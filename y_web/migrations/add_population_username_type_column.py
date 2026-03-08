"""
Database migration script to add username_type column to population table.

This script adds:
- population.username_type: TEXT/VARCHAR column to distinguish populations intended for
  microblogging vs forum (Reddit-like) experiments.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path: str) -> bool:
    """
    Add username_type column to population table in SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        bool: True if successful, False otherwise
    """
    if not db_path or not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(population)")
        columns = [row[1] for row in cursor.fetchall()]

        if "username_type" not in columns:
            cursor.execute(
                "ALTER TABLE population ADD COLUMN username_type TEXT DEFAULT 'microblogging'"
            )
            print("✓ Added username_type column to population table in SQLite database")
        else:
            print("○ username_type column already exists in population table")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host: str, port: str, database: str, user: str, password: str) -> bool:
    """
    Add username_type column to population table in PostgreSQL database.

    Args:
        host: PostgreSQL server host
        port: PostgreSQL server port
        database: Database name
        user: Database user
        password: Database password

    Returns:
        bool: True if successful, False otherwise
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'population'
        """
        )
        columns = {row[0] for row in cursor.fetchall()}

        if "username_type" not in columns:
            cursor.execute(
                """
                ALTER TABLE population
                ADD COLUMN username_type VARCHAR(20) DEFAULT 'microblogging'
            """
            )
            print(
                "✓ Added username_type column to population table in PostgreSQL database"
            )
        else:
            print("○ username_type column already exists in population table")

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False

