from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "LOGIN_DISABLED": True,
        }
    )

    LoginManager(app)

    from y_web.routes_api.reddit import api_reddit

    app.register_blueprint(api_reddit)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_api_post_uses_title_and_body_payload(client):
    with patch("y_web.routes_api.reddit.create_post_reddit") as mock_create:
        mock_create.return_value = SimpleNamespace(id=42)
        resp = client.post(
            "/api/reddit/1/post",
            json={"title": "Hello", "body": "World", "url": "https://example.com"},
        )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["data"]["post_id"] == 42

    args = mock_create.call_args[0]
    assert args[1] == "TITLE: Hello\n\nWorld"
    assert args[2] == "https://example.com"


def test_api_post_falls_back_to_legacy_content(client):
    with patch("y_web.routes_api.reddit.create_post_reddit") as mock_create:
        mock_create.return_value = SimpleNamespace(id=7)
        resp = client.post("/api/reddit/1/post", json={"content": "Legacy post"})

    assert resp.status_code == 200
    args = mock_create.call_args[0]
    assert args[1] == "Legacy post"


def test_api_post_rejects_empty_payload(client):
    resp = client.post("/api/reddit/1/post", json={})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
