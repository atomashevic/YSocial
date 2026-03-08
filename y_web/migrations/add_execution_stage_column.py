"""
Database migration script to add execution_stage column to client_execution table.

This script adds:
- execution_stage: String column (default 'initializing')
  Values: 'initializing', 'agents_loaded', 'running'

This column tracks the execution stage to properly handle resume vs fresh start:
- 'initializing': Client record created, but agents not yet loaded
- 'agents_loaded': Agents successfully loaded from server
- 'running': Simulation actively running

If a crash occurs during 'initializing' stage, the next run will restart fresh
rather than trying to resume (which would fail due to missing agents).

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
    Add execution_stage column to SQLite database.

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

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='client_execution'"
        )
        if not cursor.fetchone():
            print("○ client_execution table does not exist yet")
            conn.close()
            return True

        # Check if column already exists
        cursor.execute("PRAGMA table_info(client_execution)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add execution_stage column if it doesn't exist
        if "execution_stage" not in columns:
            cursor.execute(
                "ALTER TABLE client_execution ADD COLUMN execution_stage TEXT DEFAULT 'initializing'"
            )
            print("✓ Added execution_stage column to SQLite database")

            # Update existing records based on their elapsed_time
            # Records with elapsed_time > 0 were successful, set to 'running'
            # Records with elapsed_time = 0 may have failed during init, set to 'initializing'
            cursor.execute(
                "UPDATE client_execution SET execution_stage = 'running' WHERE elapsed_time > 0"
            )
            cursor.execute(
                "UPDATE client_execution SET execution_stage = 'initializing' WHERE elapsed_time = 0 OR elapsed_time IS NULL"
            )
            print("✓ Updated execution_stage for existing records")
        else:
            print("○ execution_stage column already exists in SQLite database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating SQLite database: {e}")
        return False


def migrate_postgresql(host, port, database, user, password):
    """
    Add execution_stage column to PostgreSQL database.

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

        # Check if table exists
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'client_execution'
        """
        )
        if not cursor.fetchone():
            print("○ client_execution table does not exist yet")
            conn.close()
            return True

        # Check if column already exists
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'client_execution'
        """
        )
        columns = [row[0] for row in cursor.fetchall()]

        # Add execution_stage column if it doesn't exist
        if "execution_stage" not in columns:
            cursor.execute(
                """
                ALTER TABLE client_execution
                ADD COLUMN execution_stage VARCHAR(20) DEFAULT 'initializing'
            """
            )
            print("✓ Added execution_stage column to PostgreSQL database")

            # Update existing records based on their elapsed_time
            cursor.execute(
                "UPDATE client_execution SET execution_stage = 'running' WHERE elapsed_time > 0"
            )
            cursor.execute(
                "UPDATE client_execution SET execution_stage = 'initializing' WHERE elapsed_time = 0 OR elapsed_time IS NULL"
            )
            print("✓ Updated execution_stage for existing records")
        else:
            print("○ execution_stage column already exists in PostgreSQL database")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL database: {e}")
        return False


def main():
    """Run migration for both SQLite and PostgreSQL databases."""
    print("YSocial Database Migration: Adding Execution Stage Column")
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
