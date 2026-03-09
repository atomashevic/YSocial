import os
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash


@pytest.fixture
def app(tmp_path):
    import y_web
    from y_web import db

    templates_dir = os.path.join(os.path.dirname(y_web.__file__), "templates")
    static_dir = os.path.join(os.path.dirname(y_web.__file__), "static")

    admin_db = tmp_path / "admin.db"
    exp_db = tmp_path / "exp.db"

    app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            # Bypass @login_required in these route tests.
            "LOGIN_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{admin_db}",
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{admin_db}",
                "db_exp": f"sqlite:///{exp_db}",
            },
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    db.init_app(app)
    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        # Minimal loader to satisfy flask-login's template context processor.
        from y_web.models import User_mgmt

        try:
            return User_mgmt.query.get(int(user_id))
        except Exception:
            return None

    from y_web.auth import auth as auth_blueprint
    from y_web.main import main as main_blueprint

    app.register_blueprint(main_blueprint)
    app.register_blueprint(auth_blueprint)

    with app.app_context():
        from y_web.models import (
            Admin_users,
            Exps,
            Post,
            ReplyInboxState,
            Rounds,
            User_mgmt,
        )

        db.create_all(bind="db_admin")
        db.create_all(bind="db_exp")

        # Forum experiment.
        exp = Exps(
            idexp=1,
            platform_type="forum",
            exp_name="Forum",
            db_name="exp_db",
            owner="test",
            exp_descr="test",
            status=1,
            running=0,
            port=8080,
            server="127.0.0.1",
            annotations="",
        )
        db.session.add(exp)

        # Admin + experiment users must share username for helper functions.
        alice_admin = Admin_users(
            username="alice",
            email="alice@test.com",
            password=generate_password_hash("pw"),
            role="user",
            last_seen="2023-01-01",
        )
        bob_admin = Admin_users(
            username="bob",
            email="bob@test.com",
            password=generate_password_hash("pw"),
            role="user",
            last_seen="2023-01-01",
        )
        db.session.add(alice_admin)
        db.session.add(bob_admin)

        alice = User_mgmt(
            username="alice",
            email="alice@test.com",
            password=generate_password_hash("pw"),
            joined_on=0,
        )
        bob = User_mgmt(
            username="bob",
            email="bob@test.com",
            password=generate_password_hash("pw"),
            joined_on=0,
        )
        db.session.add(alice)
        db.session.add(bob)

        r = Rounds(day=1, hour=1)
        db.session.add(r)
        db.session.commit()

        # Root post by alice.
        root = Post(tweet="root", round=r.id, user_id=alice.id, comment_to=-1)
        db.session.add(root)
        db.session.commit()
        root.thread_id = root.id
        db.session.commit()

        # Alice comment on her own post.
        alice_comment = Post(
            tweet="alice comment",
            round=r.id,
            user_id=alice.id,
            comment_to=root.id,
            thread_id=root.thread_id,
        )
        db.session.add(alice_comment)
        db.session.commit()

        # Bob replies to alice's root + comment (two notifications).
        bob_reply_1 = Post(
            tweet="bob reply 1",
            round=r.id,
            user_id=bob.id,
            comment_to=root.id,
            thread_id=root.thread_id,
        )
        bob_reply_2 = Post(
            tweet="bob reply 2",
            round=r.id,
            user_id=bob.id,
            comment_to=alice_comment.id,
            thread_id=root.thread_id,
        )
        db.session.add(bob_reply_1)
        db.session.add(bob_reply_2)

        # Self-reply should be excluded.
        self_reply = Post(
            tweet="alice self reply",
            round=r.id,
            user_id=alice.id,
            comment_to=root.id,
            thread_id=root.thread_id,
        )
        db.session.add(self_reply)
        db.session.commit()

        # Ensure empty state row doesn't exist yet.
        assert ReplyInboxState.query.filter_by(user_id=alice.id).first() is None

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


class _StubUser:
    def __init__(self, user_id: int, username: str):
        self.id = user_id
        self.username = username

    def get_id(self):
        return str(self.id)


def test_notifications_mark_read_and_exclude_self_reply(app, client):
    from y_web import db
    from y_web.models import Post, ReplyInboxState, User_mgmt

    with app.app_context():
        alice = User_mgmt.query.filter_by(username="alice").first()
        assert alice is not None

        root = Post.query.filter_by(user_id=alice.id, tweet="root").first()
        alice_comment = Post.query.filter_by(
            user_id=alice.id, tweet="alice comment"
        ).first()
        assert root is not None
        assert alice_comment is not None

        # Grab the self-reply id so we can ensure it doesn't appear.
        self_reply = Post.query.filter_by(
            user_id=alice.id, tweet="alice self reply"
        ).first()
        assert self_reply is not None

        expected_max_reply_id = (
            db.session.query(db.func.max(Post.id))
            .filter(
                Post.user_id != alice.id,
                Post.comment_to.in_([root.id, alice_comment.id]),
            )
            .scalar()
        )
        expected_max_reply_id = int(expected_max_reply_id or 0)
        assert expected_max_reply_id > 0

        with patch("y_web.main.current_user", _StubUser(alice.id, "alice")):
            # First open: two unread replies (bob), self-reply excluded.
            resp1 = client.get("/1/rnotifications")
            assert resp1.status_code == 200
            html1 = resp1.get_data(as_text=True)
            assert html1.count("reply-notif-item is-unread") == 2
            assert f"/1/rthread/{self_reply.id}" not in html1

            state = ReplyInboxState.query.filter_by(user_id=alice.id).first()
            assert state is not None
            assert int(state.last_seen_reply_id) == expected_max_reply_id

            # Second open: nothing should be flagged unread.
            resp2 = client.get("/1/rnotifications")
            assert resp2.status_code == 200
            html2 = resp2.get_data(as_text=True)
            assert html2.count("reply-notif-item is-unread") == 0
