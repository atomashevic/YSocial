"""
Ensure experiment post tables have a created_at timestamp column.

This migration targets experiment databases (db_exp bind), not the dashboard DB.
For legacy rows, created_at is backfilled from simulation round day/hour with
minute precision set to :00. New rows rely on database defaults/app inserts.
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


def migrate_sqlite_experiment_db(db_uri_or_path: str) -> bool:
    """
    Add post.created_at for a SQLite experiment DB and backfill legacy rows.
    """
    db_path = _sqlite_path_from_uri(db_uri_or_path)
    if not db_path or not os.path.exists(db_path):
        print(f"○ SQLite experiment DB not found for created_at migration: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if not _table_exists(cursor, "post"):
            conn.close()
            print("○ post table does not exist yet in SQLite experiment DB")
            return True

        if not _column_exists(cursor, "post", "created_at"):
            cursor.execute("ALTER TABLE post ADD COLUMN created_at DATETIME")
            print("✓ Added created_at column to post table (SQLite experiment DB)")
        else:
            print("○ created_at column already exists in post table (SQLite experiment DB)")

        # Backfill from simulation rounds when possible.
        if _table_exists(cursor, "rounds"):
            cursor.execute(
                """
                UPDATE post
                SET created_at = (
                    SELECT datetime(
                        date('now', 'localtime'),
                        printf('+%d days', CASE WHEN rounds.day < 0 THEN 0 ELSE rounds.day END),
                        printf(
                            '+%d hours',
                            CASE
                                WHEN rounds.hour < 0 THEN 0
                                WHEN rounds.hour > 23 THEN 23
                                ELSE rounds.hour
                            END
                        )
                    )
                    FROM rounds
                    WHERE rounds.id = post.round
                )
                WHERE created_at IS NULL
                """
            )

        # Final fallback for any unresolved legacy rows.
        cursor.execute(
            "UPDATE post SET created_at = datetime('now', 'localtime') WHERE created_at IS NULL"
        )

        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"✗ Error migrating SQLite experiment DB post.created_at: {exc}")
        return False

