"""
Media upload serving routes.

We store user uploads under a writable directory and serve them via
the dedicated /uploads route.
"""

from __future__ import annotations

import os

from flask import Blueprint, abort, send_from_directory
from werkzeug.utils import safe_join

from y_web.utils.path_utils import get_writable_path


uploads = Blueprint("uploads", __name__)


def _uploads_base_dir() -> str:
    return os.path.join(get_writable_path(), "y_web", "uploads")


@uploads.get("/uploads/<path:relpath>")
def serve_upload(relpath: str):
    base_dir = _uploads_base_dir()
    safe_path = safe_join(base_dir, relpath)
    if not safe_path:
        abort(404)

    return send_from_directory(base_dir, relpath)
