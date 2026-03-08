"""
Ensure experiment post tables support idempotent comment deduplication.

Targets SQLite experiment databases (db_exp bind). Adds nullable dedupe columns
and unique partial indexes that apply only to new rows where dedupe values are set.
"""

from __future__ import annotations

import os
import sqlite3


def _sqlite_path_from_uri(db_uri_or_path: str) -> str:
    if db_uri_or_path.startswith("sqlite:///"):
        return db_uri_or_path[len("sqlite:///"):]
    return db_uri_or_path


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def migrate_sqlite_comment_dedupe_columns(db_uri_or_path: str) -> bool:
    db_path = _sqlite_path_from_uri(db_uri_or_path)
    if not db_path or not os.path.exists(db_path):
        print(f"○ SQLite experiment DB not found for comment dedupe migration: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if not _table_exists(cursor, "post"):
            conn.close()
            print("○ post table does not exist yet in SQLite experiment DB")
            return True

        if not _column_exists(cursor, "post", "dedupe_key"):
            cursor.execute("ALTER TABLE post ADD COLUMN dedupe_key TEXT")
            print("✓ Added dedupe_key column to post table (SQLite experiment DB)")
        else:
            print("○ dedupe_key column already exists in post table (SQLite experiment DB)")

        if not _column_exists(cursor, "post", "client_action_id"):
            cursor.execute("ALTER TABLE post ADD COLUMN client_action_id TEXT")
            print("✓ Added client_action_id column to post table (SQLite experiment DB)")
        else:
            print(
                "○ client_action_id column already exists in post table (SQLite experiment DB)"
            )

        # Apply unique partial indexes only where dedupe values are present.
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_post_comment_action_id_uniq
            ON post (user_id, client_action_id)
            WHERE client_action_id IS NOT NULL
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_post_comment_dedupe_uniq
            ON post (user_id, comment_to, round, dedupe_key)
            WHERE comment_to <> -1 AND dedupe_key IS NOT NULL
            """
        )

        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating SQLite experiment DB comment dedupe columns: {exc}")
        return False

