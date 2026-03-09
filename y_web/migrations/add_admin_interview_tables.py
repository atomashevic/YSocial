"""
Database migration script for admin interview dashboard tables.

This migration ensures the dashboard DB has the admin interview tables used by
the interview UI and backfills additive columns/indexes for older deployments.
"""

import os
import sqlite3

try:
    import psycopg2

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


SESSION_INDEXES = (
    ("ix_admin_interview_sessions_exp_id", "exp_id"),
    ("ix_admin_interview_sessions_admin_username", "admin_username"),
    ("ix_admin_interview_sessions_run_id", "run_id"),
)

MESSAGE_INDEXES = (("ix_admin_interview_messages_session_id", "session_id"),)


def _sqlite_table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _sqlite_index_exists(cursor, index_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    return cursor.fetchone() is not None


def _sqlite_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _postgresql_table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _postgresql_index_exists(cursor, index_name):
    cursor.execute(
        """
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = %s
        """,
        (index_name,),
    )
    return cursor.fetchone() is not None


def _postgresql_columns(cursor, table_name):
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0] for row in cursor.fetchall()}


def _ensure_sqlite_session_table(cursor):
    if not _sqlite_table_exists(cursor, "admin_interview_sessions"):
        cursor.execute("""
            CREATE TABLE admin_interview_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exp_id INTEGER NOT NULL,
                admin_username TEXT NOT NULL,
                agent_user_id INTEGER NOT NULL,
                agent_username TEXT NOT NULL,
                run_id TEXT,
                backend_mode TEXT NOT NULL DEFAULT 'agent_runtime',
                llm_model TEXT,
                llm_base_url TEXT,
                persona_snapshot TEXT,
                interests_snapshot_json TEXT,
                memory_snapshot_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        print("✓ Created admin_interview_sessions table in SQLite database")
        return

    columns = _sqlite_columns(cursor, "admin_interview_sessions")
    if "run_id" not in columns:
        cursor.execute("ALTER TABLE admin_interview_sessions ADD COLUMN run_id TEXT")
        print("✓ Added run_id column to admin_interview_sessions")
    if "backend_mode" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN backend_mode TEXT DEFAULT 'agent_runtime'
            """)
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET backend_mode = 'agent_runtime'
            WHERE backend_mode IS NULL
            """)
        print("✓ Added backend_mode column to admin_interview_sessions")
    if "llm_model" not in columns:
        cursor.execute("ALTER TABLE admin_interview_sessions ADD COLUMN llm_model TEXT")
        print("✓ Added llm_model column to admin_interview_sessions")
    if "llm_base_url" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_sessions ADD COLUMN llm_base_url TEXT"
        )
        print("✓ Added llm_base_url column to admin_interview_sessions")
    if "persona_snapshot" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_sessions ADD COLUMN persona_snapshot TEXT"
        )
        print("✓ Added persona_snapshot column to admin_interview_sessions")
    if "interests_snapshot_json" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN interests_snapshot_json TEXT
            """)
        print("✓ Added interests_snapshot_json column to admin_interview_sessions")
    if "memory_snapshot_json" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN memory_snapshot_json TEXT
            """)
        print("✓ Added memory_snapshot_json column to admin_interview_sessions")
    if "created_at" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_sessions ADD COLUMN created_at DATETIME"
        )
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """)
        print("✓ Added created_at column to admin_interview_sessions")
    if "updated_at" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_sessions ADD COLUMN updated_at DATETIME"
        )
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL
            """)
        print("✓ Added updated_at column to admin_interview_sessions")


def _ensure_sqlite_message_table(cursor):
    if not _sqlite_table_exists(cursor, "admin_interview_messages"):
        cursor.execute("""
            CREATE TABLE admin_interview_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                meta_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES admin_interview_sessions(id)
            )
            """)
        print("✓ Created admin_interview_messages table in SQLite database")
        return

    columns = _sqlite_columns(cursor, "admin_interview_messages")
    if "meta_json" not in columns:
        cursor.execute("ALTER TABLE admin_interview_messages ADD COLUMN meta_json TEXT")
        print("✓ Added meta_json column to admin_interview_messages")
    if "created_at" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_messages ADD COLUMN created_at DATETIME"
        )
        cursor.execute("""
            UPDATE admin_interview_messages
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """)
        print("✓ Added created_at column to admin_interview_messages")


def _ensure_sqlite_indexes(cursor):
    for index_name, column_name in SESSION_INDEXES:
        if not _sqlite_index_exists(cursor, index_name):
            cursor.execute(f"""
                CREATE INDEX {index_name}
                ON admin_interview_sessions ({column_name})
                """)
            print(f"✓ Created {index_name} index")
    for index_name, column_name in MESSAGE_INDEXES:
        if not _sqlite_index_exists(cursor, index_name):
            cursor.execute(f"""
                CREATE INDEX {index_name}
                ON admin_interview_messages ({column_name})
                """)
            print(f"✓ Created {index_name} index")


def migrate_sqlite(db_path):
    """
    Ensure SQLite dashboard DB has admin interview tables and columns.
    """
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        _ensure_sqlite_session_table(cursor)
        _ensure_sqlite_message_table(cursor)
        _ensure_sqlite_indexes(cursor)

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Error migrating SQLite admin interview tables: {e}")
        return False


def _ensure_postgresql_session_table(cursor):
    if not _postgresql_table_exists(cursor, "admin_interview_sessions"):
        cursor.execute("""
            CREATE TABLE admin_interview_sessions (
                id SERIAL PRIMARY KEY,
                exp_id INTEGER NOT NULL,
                admin_username VARCHAR(50) NOT NULL,
                agent_user_id INTEGER NOT NULL,
                agent_username VARCHAR(50) NOT NULL,
                run_id TEXT,
                backend_mode VARCHAR(20) NOT NULL DEFAULT 'agent_runtime',
                llm_model VARCHAR(200),
                llm_base_url VARCHAR(300),
                persona_snapshot TEXT,
                interests_snapshot_json TEXT,
                memory_snapshot_json TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        print("✓ Created admin_interview_sessions table in PostgreSQL database")
        return

    columns = _postgresql_columns(cursor, "admin_interview_sessions")
    if "run_id" not in columns:
        cursor.execute("ALTER TABLE admin_interview_sessions ADD COLUMN run_id TEXT")
        print("✓ Added run_id column to admin_interview_sessions")
    if "backend_mode" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN backend_mode VARCHAR(20) DEFAULT 'agent_runtime'
            """)
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET backend_mode = 'agent_runtime'
            WHERE backend_mode IS NULL
            """)
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ALTER COLUMN backend_mode SET NOT NULL
            """)
        print("✓ Added backend_mode column to admin_interview_sessions")
    if "llm_model" not in columns:
        cursor.execute(
            "ALTER TABLE admin_interview_sessions ADD COLUMN llm_model VARCHAR(200)"
        )
        print("✓ Added llm_model column to admin_interview_sessions")
    if "llm_base_url" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN llm_base_url VARCHAR(300)
            """)
        print("✓ Added llm_base_url column to admin_interview_sessions")
    if "persona_snapshot" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN persona_snapshot TEXT
            """)
        print("✓ Added persona_snapshot column to admin_interview_sessions")
    if "interests_snapshot_json" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN interests_snapshot_json TEXT
            """)
        print("✓ Added interests_snapshot_json column to admin_interview_sessions")
    if "memory_snapshot_json" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN memory_snapshot_json TEXT
            """)
        print("✓ Added memory_snapshot_json column to admin_interview_sessions")
    if "created_at" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """)
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ALTER COLUMN created_at SET NOT NULL
            """)
        print("✓ Added created_at column to admin_interview_sessions")
    if "updated_at" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)
        cursor.execute("""
            UPDATE admin_interview_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE updated_at IS NULL
            """)
        cursor.execute("""
            ALTER TABLE admin_interview_sessions
            ALTER COLUMN updated_at SET NOT NULL
            """)
        print("✓ Added updated_at column to admin_interview_sessions")


def _ensure_postgresql_message_table(cursor):
    if not _postgresql_table_exists(cursor, "admin_interview_messages"):
        cursor.execute("""
            CREATE TABLE admin_interview_messages (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL
                    REFERENCES admin_interview_sessions(id),
                role VARCHAR(12) NOT NULL,
                content TEXT NOT NULL,
                meta_json TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """)
        print("✓ Created admin_interview_messages table in PostgreSQL database")
        return

    columns = _postgresql_columns(cursor, "admin_interview_messages")
    if "meta_json" not in columns:
        cursor.execute("ALTER TABLE admin_interview_messages ADD COLUMN meta_json TEXT")
        print("✓ Added meta_json column to admin_interview_messages")
    if "created_at" not in columns:
        cursor.execute("""
            ALTER TABLE admin_interview_messages
            ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """)
        cursor.execute("""
            UPDATE admin_interview_messages
            SET created_at = CURRENT_TIMESTAMP
            WHERE created_at IS NULL
            """)
        cursor.execute("""
            ALTER TABLE admin_interview_messages
            ALTER COLUMN created_at SET NOT NULL
            """)
        print("✓ Added created_at column to admin_interview_messages")


def _ensure_postgresql_indexes(cursor):
    for index_name, column_name in SESSION_INDEXES:
        if not _postgresql_index_exists(cursor, index_name):
            cursor.execute(f"""
                CREATE INDEX {index_name}
                ON admin_interview_sessions ({column_name})
                """)
            print(f"✓ Created {index_name} index")
    for index_name, column_name in MESSAGE_INDEXES:
        if not _postgresql_index_exists(cursor, index_name):
            cursor.execute(f"""
                CREATE INDEX {index_name}
                ON admin_interview_messages ({column_name})
                """)
            print(f"✓ Created {index_name} index")


def migrate_postgresql(host, port, database, user, password):
    """
    Ensure PostgreSQL dashboard DB has admin interview tables and columns.
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    conn = None
    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cursor = conn.cursor()

        _ensure_postgresql_session_table(cursor)
        _ensure_postgresql_message_table(cursor)
        _ensure_postgresql_indexes(cursor)

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        if conn is not None:
            conn.rollback()
            conn.close()
        print(f"✗ Error migrating PostgreSQL admin interview tables: {e}")
        return False
