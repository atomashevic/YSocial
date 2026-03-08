import struct
from io import BytesIO
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from PIL import Image


@pytest.fixture
def app(tmp_path):
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
    from y_web.routes_uploads import uploads

    app.register_blueprint(api_reddit)
    app.register_blueprint(uploads)

    with (
        patch("y_web.routes_api.reddit.get_writable_path", return_value=str(tmp_path)),
        patch("y_web.routes_uploads.get_writable_path", return_value=str(tmp_path)),
    ):
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def _png_bytes():
    bio = BytesIO()
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio


def _mp4_bytes(duration_seconds=5):
    timescale = 1000
    duration = max(1, int(duration_seconds * timescale))
    ftyp_payload = b"isom" + b"\x00\x00\x02\x00" + b"isomiso2"
    ftyp = struct.pack(">I4s", 8 + len(ftyp_payload), b"ftyp") + ftyp_payload

    mvhd_payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + struct.pack(">I", timescale)
        + struct.pack(">I", duration)
        + (b"\x00" * 80)
    )
    mvhd = struct.pack(">I4s", 8 + len(mvhd_payload), b"mvhd") + mvhd_payload
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd

    bio = BytesIO(ftyp + moov)
    bio.seek(0)
    return bio


def test_upload_image_success_and_servable(client):
    resp = client.post(
        "/api/reddit/1/upload_image",
        data={"file": (_png_bytes(), "test.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    url = data["data"]["url"]
    assert url.startswith("/uploads/reddit/1/")

    img_resp = client.get(url)
    assert img_resp.status_code == 200
    assert img_resp.data


def test_upload_media_mp4_success_and_servable(client):
    resp = client.post(
        "/api/reddit/1/upload_media",
        data={"file": (_mp4_bytes(), "clip.mp4")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    url = data["data"]["url"]
    assert url.startswith("/uploads/reddit/1/")
    assert url.endswith(".mp4")

    media_resp = client.get(url)
    assert media_resp.status_code == 200
    assert media_resp.data


def test_upload_image_mp4_backward_compatible_success(client):
    resp = client.post(
        "/api/reddit/1/upload_image",
        data={"file": (_mp4_bytes(), "clip.mp4")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["data"]["url"].endswith(".mp4")


def test_upload_image_rejects_unsupported_extension(client):
    resp = client.post(
        "/api/reddit/1/upload_image",
        data={"file": (BytesIO(b"hello"), "note.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 415
    data = resp.get_json()
    assert data["success"] is False


def test_upload_image_rejects_invalid_image_payload(client):
    resp = client.post(
        "/api/reddit/1/upload_image",
        data={"file": (BytesIO(b"not an image"), "fake.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_upload_media_rejects_invalid_mp4_payload(client):
    resp = client.post(
        "/api/reddit/1/upload_media",
        data={"file": (BytesIO(b"not an mp4"), "fake.mp4")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_upload_media_rejects_mp4_too_long(client):
    resp = client.post(
        "/api/reddit/1/upload_media",
        data={"file": (_mp4_bytes(duration_seconds=31), "long.mp4")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert data["success"] is False


def test_upload_image_rejects_too_large(client):
    payload = BytesIO(b"a" * (10 * 1024 * 1024 + 1))
    resp = client.post(
        "/api/reddit/1/upload_image",
        data={"file": (payload, "big.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert data["success"] is False
