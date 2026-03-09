import os
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    admin_db = tmp_path / "admin.db"
    exp_db = tmp_path / "exp.db"
    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "LOGIN_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{admin_db}",
            "SQLALCHEMY_BINDS": {
                "db_admin": f"sqlite:///{admin_db}",
                "db_exp": f"sqlite:///{exp_db}",
            },
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )

    LoginManager(app)

    from y_web import db
    from y_web.models import Admin_users, Articles, Images, Websites
    from y_web.routes_api.reddit import api_reddit

    db.init_app(app)
    app.register_blueprint(api_reddit)

    with app.app_context():
        db.session.remove()
        db.create_all(bind="db_admin")
        db.create_all(bind="db_exp")

        admin_user = Admin_users(
            username="admin",
            email="admin@test.com",
            password=generate_password_hash("admin123"),
            role="admin",
            last_seen="2023-01-01",
            llm="llama3.2:latest",
            llm_url="",
        )
        db.session.add(admin_user)

        website = Websites(
            name="Example",
            rss="",
            leaning="neutral",
            category="user_shared",
            last_fetched=0,
            language="en",
            country="us",
        )
        db.session.add(website)
        db.session.commit()

        article = Articles(
            title="Example Title",
            summary="User shared article",
            website_id=website.id,
            link="https://example.com/story",
            fetched_on=0,
        )
        db.session.add(article)

        image = Images(
            url="/uploads/reddit/1/test.png", description=None, article_id=None
        )
        db.session.add(image)
        db.session.commit()

    with patch("y_web.routes_api.reddit.get_writable_path", return_value=str(tmp_path)):
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


class _StubUser:
    def __init__(self, username):
        self.username = username


def test_enrich_article_disabled_without_llm(client):
    with (
        patch.dict(os.environ, {"LLM_URL": "", "LLM_BACKEND": ""}, clear=False),
        patch("y_web.routes_api.reddit.current_user", _StubUser("admin")),
    ):
        resp = client.post("/api/reddit/1/enrich/article/1", json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["enabled"] is False


def test_enrich_article_updates_summary_when_enabled(client):
    from y_web import db
    from y_web.models import Admin_users, Articles

    with client.application.app_context():
        admin = Admin_users.query.filter_by(username="admin").first()
        admin.llm_url = "localhost:11434"
        db.session.commit()

        with (
            patch("y_web.routes_api.reddit.current_user", _StubUser("admin")),
            patch(
                "y_web.routes_api.reddit.UrlSummarizer.summarize_url",
                return_value=(
                    "LLM upgraded summary that is long enough to be treated as cached "
                    "by the enrichment heuristic."
                ),
            ),
        ):
            resp = client.post("/api/reddit/1/enrich/article/1", json={})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["ok"] is True
    assert "LLM upgraded summary" in payload["data"]["summary"]

    with client.application.app_context():
        art = Articles.query.get(1)
        assert "LLM upgraded summary" in art.summary

    with patch("y_web.routes_api.reddit.current_user", _StubUser("admin")):
        resp2 = client.post("/api/reddit/1/enrich/article/1", json={})
    assert resp2.status_code == 200
    payload2 = resp2.get_json()
    assert payload2["success"] is True
    assert payload2["data"]["ok"] is True
    assert payload2["data"]["cached"] is True


def test_enrich_image_disabled_without_llm(client):
    with (
        patch.dict(os.environ, {"LLM_URL": "", "LLM_BACKEND": ""}, clear=False),
        patch("y_web.routes_api.reddit.current_user", _StubUser("admin")),
    ):
        resp = client.post("/api/reddit/1/enrich/image/1", json={})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["enabled"] is False


def test_enrich_image_maps_upload_to_local_path_and_updates_description(
    client, tmp_path
):
    from y_web import db
    from y_web.models import Admin_users, Images

    upload_path = tmp_path / "y_web" / "uploads" / "reddit" / "1"
    upload_path.mkdir(parents=True, exist_ok=True)
    img_file = upload_path / "test.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    with client.application.app_context():
        admin = Admin_users.query.filter_by(username="admin").first()
        admin.llm_url = "http://localhost:11434/v1"
        db.session.commit()

    seen = {}

    def _fake_annotate(arg):
        seen["arg"] = arg
        return "A short description."

    with (
        patch("y_web.routes_api.reddit.current_user", _StubUser("admin")),
        patch("y_web.routes_api.reddit.Annotator.annotate", side_effect=_fake_annotate),
    ):
        resp = client.post("/api/reddit/1/enrich/image/1", json={})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["ok"] is True
    assert payload["data"]["description"] == "A short description."
    assert os.path.exists(seen["arg"])

    with client.application.app_context():
        img = Images.query.get(1)
        assert img.description == "A short description."


def test_enrich_image_rejects_path_traversal(client):
    from y_web import db
    from y_web.models import Admin_users, Images

    with client.application.app_context():
        admin = Admin_users.query.filter_by(username="admin").first()
        admin.llm_url = "http://localhost:11434/v1"
        img = Images(url="/uploads/../secret.png", description=None, article_id=None)
        db.session.add(img)
        db.session.commit()
        bad_id = img.id

    with patch("y_web.routes_api.reddit.current_user", _StubUser("admin")):
        resp = client.post(f"/api/reddit/1/enrich/image/{bad_id}", json={})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
