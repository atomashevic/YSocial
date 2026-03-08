"""
Database migration script to add activity_profile columns to agents and pages tables.

This script adds:
- activity_profile: Integer column (FK to activity_profiles.id) to agents table
- activity_profile: Integer column (FK to activity_profiles.id) to pages table

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
    Add activity_profile columns to SQLite database.

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

        # Check agents table columns
        cursor.execute("PRAGMA table_info(agents)")
        agents_columns = [row[1] for row in cursor.fetchall()]

        # Add activity_profile column to agents if it doesn't exist
        if "activity_profile" not in agents_columns:
            cursor.execute(
                "ALTER TABLE agents ADD COLUMN activity_profile INTEGER"
            )
            print("✓ Added activity_profile column to agents table in SQLite database")
        else:
            print("○ activity_profile column already exists in agents table")

        # Check pages table columns
        cursor.execute("PRAGMA table_info(pages)")
        pages_columns = [row[1] for row in cursor.fetchall()]

        # Add activity_profile column to pages if it doesn't exist
        if "activity_profile" not in pages_columns:
            cursor.execute(
                "ALTER TABLE pages ADD COLUMN activity_profile INTEGER"
            )
            print("✓ Added activity_profile column to pages table in SQLite database")
        else:
            print("○ activity_profile column already exists in pages table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add activity_profile columns to PostgreSQL database.

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

        # Check agents table columns
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'agents'
        """
        )
        agents_columns = [row[0] for row in cursor.fetchall()]

        # Add activity_profile column to agents if it doesn't exist
        if "activity_profile" not in agents_columns:
            cursor.execute(
                """
                ALTER TABLE agents
                ADD COLUMN activity_profile INTEGER REFERENCES activity_profiles(id)
            """
            )
            print("✓ Added activity_profile column to agents table in PostgreSQL database")
        else:
            print("○ activity_profile column already exists in agents table")

        # Check pages table columns
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'pages'
        """
        )
        pages_columns = [row[0] for row in cursor.fetchall()]

        # Add activity_profile column to pages if it doesn't exist
        if "activity_profile" not in pages_columns:
            cursor.execute(
                """
                ALTER TABLE pages
                ADD COLUMN activity_profile INTEGER REFERENCES activity_profiles(id)
            """
            )
            print("✓ Added activity_profile column to pages table in PostgreSQL database")
        else:
            print("○ activity_profile column already exists in pages table")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Activity Profile Columns")
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
