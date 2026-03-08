"""
Avatar/icon utilities.

Centralizes avatar selection so forum experiments give both LLM agents and
admin-created "real" users the same style of icons.
"""

from __future__ import annotations

import os
import random
from typing import List


def discover_forum_avatar_urls() -> List[str]:
    """
    Return a list of static URLs for forum avatar icons, if present.

    Looks for files in: y_web/static/assets/img/reddit/avatars/
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        avatars_dir = os.path.normpath(
            os.path.join(
                base_dir,
                "..",
                "static",
                "assets",
                "img",
                "reddit",
                "avatars",
            )
        )
        if not os.path.isdir(avatars_dir):
            return []
        files = [
            f
            for f in os.listdir(avatars_dir)
            if os.path.isfile(os.path.join(avatars_dir, f))
            and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
            and not f.startswith(".")
        ]
        files.sort()
        return [f"/static/assets/img/reddit/avatars/{f}" for f in files]
    except Exception:
        return []


def pick_forum_avatar_url() -> str:
    """Pick a reddit-style forum avatar URL from the static icon pool."""
    urls = discover_forum_avatar_urls()
    if not urls:
        return ""
    return random.choice(urls)


def deterministic_forum_avatar_url(username: str) -> str:
    """Pick a forum avatar deterministically based on username hash."""
    urls = discover_forum_avatar_urls()
    if not urls:
        return ""
    return urls[hash(username) % len(urls)]
