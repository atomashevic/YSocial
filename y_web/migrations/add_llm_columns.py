"""
Database migration script to add LLM configuration columns to exps and client tables.

This script adds:
- LLM default columns to exps table (for experiment-wide LLM configuration)
- Reply behavior columns to client table (if missing)

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
    Add LLM columns to exps table and reply behavior columns to client table in SQLite database.

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

        # Get existing columns in exps table
        cursor.execute("PRAGMA table_info(exps)")
        exps_columns = [row[1] for row in cursor.fetchall()]

        # Add LLM default columns to exps table
        exps_columns_to_add = [
            ("llm_agents_enabled", "INTEGER DEFAULT 1"),
            ("llm_default", "VARCHAR(100) DEFAULT 'http://127.0.0.1:11434/v1'"),
            ("llm_api_key_default", "VARCHAR(300) DEFAULT 'NULL'"),
            ("llm_max_tokens_default", "INTEGER DEFAULT -1"),
            ("llm_temperature_default", "REAL DEFAULT 1.5"),
            ("llm_v_default", "VARCHAR(100) DEFAULT 'http://127.0.0.1:11434/v1'"),
            ("llm_v_api_key_default", "VARCHAR(300) DEFAULT 'NULL'"),
            ("llm_v_max_tokens_default", "INTEGER DEFAULT 300"),
            ("llm_v_temperature_default", "REAL DEFAULT 0.5"),
        ]

        added_exps_columns = []
        for col_name, col_def in exps_columns_to_add:
            if col_name not in exps_columns:
                cursor.execute(f"ALTER TABLE exps ADD COLUMN {col_name} {col_def}")
                added_exps_columns.append(col_name)

        if added_exps_columns:
            print(f"✓ Added LLM columns to exps table: {', '.join(added_exps_columns)}")
        else:
            print("○ All LLM columns already exist in exps table")

        # Get existing columns in client table
        cursor.execute("PRAGMA table_info(client)")
        client_columns = [row[1] for row in cursor.fetchall()]

        # Add reply behavior columns to client table
        client_columns_to_add = [
            ("pid", "INTEGER DEFAULT NULL"),
            ("reply_probability", "REAL DEFAULT 0.4"),
            ("max_replies_per_round", "INTEGER DEFAULT 2"),
            ("reply_cooldown_rounds", "INTEGER DEFAULT 2"),
        ]

        added_client_columns = []
        for col_name, col_def in client_columns_to_add:
            if col_name not in client_columns:
                cursor.execute(f"ALTER TABLE client ADD COLUMN {col_name} {col_def}")
                added_client_columns.append(col_name)

        if added_client_columns:
            print(
                f"✓ Added reply behavior columns to client table: {', '.join(added_client_columns)}"
            )
        else:
            print("○ All reply behavior columns already exist in client table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        import traceback

        traceback.print_exc()
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add LLM columns to exps table and reply behavior columns to client table in PostgreSQL database.

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

        # Get existing columns in exps table
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'exps'
        """)
        exps_columns = [row[0] for row in cursor.fetchall()]

        # Add LLM default columns to exps table
        exps_columns_to_add = [
            ("llm_agents_enabled", "INTEGER DEFAULT 1"),
            ("llm_default", "VARCHAR(100) DEFAULT 'http://127.0.0.1:11434/v1'"),
            ("llm_api_key_default", "VARCHAR(300) DEFAULT 'NULL'"),
            ("llm_max_tokens_default", "INTEGER DEFAULT -1"),
            ("llm_temperature_default", "REAL DEFAULT 1.5"),
            ("llm_v_default", "VARCHAR(100) DEFAULT 'http://127.0.0.1:11434/v1'"),
            ("llm_v_api_key_default", "VARCHAR(300) DEFAULT 'NULL'"),
            ("llm_v_max_tokens_default", "INTEGER DEFAULT 300"),
            ("llm_v_temperature_default", "REAL DEFAULT 0.5"),
        ]

        added_exps_columns = []
        for col_name, col_def in exps_columns_to_add:
            if col_name not in exps_columns:
                cursor.execute(f"ALTER TABLE exps ADD COLUMN {col_name} {col_def}")
                added_exps_columns.append(col_name)

        if added_exps_columns:
            print(f"✓ Added LLM columns to exps table: {', '.join(added_exps_columns)}")
        else:
            print("○ All LLM columns already exist in exps table")

        # Get existing columns in client table
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'client'
        """)
        client_columns = [row[0] for row in cursor.fetchall()]

        # Add reply behavior columns to client table
        client_columns_to_add = [
            ("pid", "INTEGER DEFAULT NULL"),
            ("reply_probability", "REAL DEFAULT 0.4"),
            ("max_replies_per_round", "INTEGER DEFAULT 2"),
            ("reply_cooldown_rounds", "INTEGER DEFAULT 2"),
        ]

        added_client_columns = []
        for col_name, col_def in client_columns_to_add:
            if col_name not in client_columns:
                cursor.execute(f"ALTER TABLE client ADD COLUMN {col_name} {col_def}")
                added_client_columns.append(col_name)

        if added_client_columns:
            print(
                f"✓ Added reply behavior columns to client table: {', '.join(added_client_columns)}"
            )
        else:
            print("○ All reply behavior columns already exist in client table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding LLM Configuration Columns")
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
