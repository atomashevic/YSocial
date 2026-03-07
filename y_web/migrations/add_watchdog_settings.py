"""
Database migration script to add watchdog_settings table for process watchdog.

This script adds the watchdog_settings table which stores:
- enabled: Whether the process watchdog is enabled
- run_interval_minutes: Frequency of watchdog runs in minutes (default 1)
- server_heartbeat_timeout_sec: Server heartbeat timeout in seconds (default 300)
- client_heartbeat_timeout_sec: Client heartbeat timeout in seconds (default 300)
- heartbeat_interval_sec: Expected heartbeat interval in seconds (default 60)
- max_restart_attempts: Max restart attempts before giving up (default 3)
- restart_cooldown_sec: Cooldown between restart attempts in seconds (default 60)
- last_run: Timestamp of the last watchdog run

Run this script to update existing YSocial installations.
"""

import os
import sqlite3
import sys

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def migrate_sqlite(db_path):
    """
    Add watchdog_settings table to SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        bool: True if successful, False otherwise
    """
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='watchdog_settings'"
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute(
                """
                CREATE TABLE watchdog_settings (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    enabled              INTEGER NOT NULL DEFAULT 1,
                    run_interval_minutes INTEGER NOT NULL DEFAULT 1,
                    server_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                    client_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                    heartbeat_interval_sec INTEGER NOT NULL DEFAULT 60,
                    max_restart_attempts INTEGER NOT NULL DEFAULT 3,
                    restart_cooldown_sec INTEGER NOT NULL DEFAULT 60,
                    last_run             TEXT
                )
            """
            )
            # Insert default settings row
            cursor.execute(
                """
                INSERT INTO watchdog_settings (
                    enabled, run_interval_minutes, server_heartbeat_timeout_sec,
                    client_heartbeat_timeout_sec, heartbeat_interval_sec,
                    max_restart_attempts, restart_cooldown_sec
                )
                VALUES (1, 1, 300, 300, 60, 3, 60)
            """
            )
            print("✓ Created watchdog_settings table in SQLite database")
        else:
            print("○ watchdog_settings table already exists in SQLite database")

            # Add missing columns for older installations
            cursor.execute("PRAGMA table_info(watchdog_settings)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            column_updates = [
                (
                    "server_heartbeat_timeout_sec",
                    "INTEGER NOT NULL DEFAULT 300",
                    300,
                ),
                (
                    "client_heartbeat_timeout_sec",
                    "INTEGER NOT NULL DEFAULT 300",
                    300,
                ),
                (
                    "heartbeat_interval_sec",
                    "INTEGER NOT NULL DEFAULT 60",
                    60,
                ),
                (
                    "max_restart_attempts",
                    "INTEGER NOT NULL DEFAULT 3",
                    3,
                ),
                (
                    "restart_cooldown_sec",
                    "INTEGER NOT NULL DEFAULT 60",
                    60,
                ),
            ]
            for col_name, col_type, default_value in column_updates:
                if col_name not in existing_cols:
                    cursor.execute(
                        f"ALTER TABLE watchdog_settings ADD COLUMN {col_name} {col_type}"
                    )
                    print(f"✓ Added {col_name} column to SQLite watchdog_settings")
                cursor.execute(
                    f"UPDATE watchdog_settings SET {col_name} = ? WHERE {col_name} IS NULL",
                    (default_value,),
                )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add watchdog_settings table to PostgreSQL database.

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
        print("  Install with: pip install psycopg2-binary")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        # Check if table already exists
        cursor.execute(
            """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name = 'watchdog_settings'
        """
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute(
                """
                CREATE TABLE watchdog_settings (
                    id                   SERIAL PRIMARY KEY,
                    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
                    run_interval_minutes INTEGER NOT NULL DEFAULT 1,
                    server_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                    client_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                    heartbeat_interval_sec INTEGER NOT NULL DEFAULT 60,
                    max_restart_attempts INTEGER NOT NULL DEFAULT 3,
                    restart_cooldown_sec INTEGER NOT NULL DEFAULT 60,
                    last_run             TIMESTAMP
                )
            """
            )
            # Insert default settings row
            cursor.execute(
                """
                INSERT INTO watchdog_settings (
                    enabled, run_interval_minutes, server_heartbeat_timeout_sec,
                    client_heartbeat_timeout_sec, heartbeat_interval_sec,
                    max_restart_attempts, restart_cooldown_sec
                )
                VALUES (TRUE, 1, 300, 300, 60, 3, 60)
            """
            )
            print("✓ Created watchdog_settings table in PostgreSQL database")
        else:
            print("○ watchdog_settings table already exists in PostgreSQL database")

            cursor.execute(
                """
                ALTER TABLE watchdog_settings
                ADD COLUMN IF NOT EXISTS server_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                ADD COLUMN IF NOT EXISTS client_heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
                ADD COLUMN IF NOT EXISTS heartbeat_interval_sec INTEGER NOT NULL DEFAULT 60,
                ADD COLUMN IF NOT EXISTS max_restart_attempts INTEGER NOT NULL DEFAULT 3,
                ADD COLUMN IF NOT EXISTS restart_cooldown_sec INTEGER NOT NULL DEFAULT 60
            """
            )
            cursor.execute(
                """
                UPDATE watchdog_settings
                SET
                    server_heartbeat_timeout_sec = COALESCE(server_heartbeat_timeout_sec, 300),
                    client_heartbeat_timeout_sec = COALESCE(client_heartbeat_timeout_sec, 300),
                    heartbeat_interval_sec = COALESCE(heartbeat_interval_sec, 60),
                    max_restart_attempts = COALESCE(max_restart_attempts, 3),
                    restart_cooldown_sec = COALESCE(restart_cooldown_sec, 60)
            """
            )

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Watchdog Settings Table")
    print("=" * 60)
    print()

    # Migrate SQLite database
    print("Migrating SQLite database...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    sqlite_db_path = os.path.join(project_root, "data_schema", "database_dashboard.db")

    sqlite_success = migrate_sqlite(sqlite_db_path)
    print()

    # Migrate PostgreSQL database (if configured)
    print("Migrating PostgreSQL database...")

    # Try to read PostgreSQL configuration from environment variables
    pg_host = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port = os.environ.get("POSTGRES_PORT", "5432")
    pg_database = os.environ.get("POSTGRES_DB", "ysocial")
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_password = os.environ.get("POSTGRES_PASSWORD", "")

    if pg_password:
        postgresql_success = migrate_postgresql(
            pg_host, pg_port, pg_database, pg_user, pg_password
        )
    else:
        print("○ PostgreSQL not configured (no password found in environment)")
        print("  To migrate PostgreSQL, set the following environment variables:")
        print("  - POSTGRES_HOST (default: localhost)")
        print("  - POSTGRES_PORT (default: 5432)")
        print("  - POSTGRES_DB (default: ysocial)")
        print("  - POSTGRES_USER (default: postgres)")
        print("  - POSTGRES_PASSWORD (required)")
        postgresql_success = None

    print()
    print("=" * 60)
    print("Migration Summary:")
    print(f"  SQLite:     {'✓ Success' if sqlite_success else '✗ Failed'}")
    if postgresql_success is not None:
        print(f"  PostgreSQL: {'✓ Success' if postgresql_success else '✗ Failed'}")
    else:
        print("  PostgreSQL: ○ Skipped (not configured)")
    print("=" * 60)

    return 0 if sqlite_success else 1


if __name__ == "__main__":
    sys.exit(main())
