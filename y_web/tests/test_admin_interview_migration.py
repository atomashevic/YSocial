import sqlite3
from pathlib import Path

from y_web.migrations.add_admin_interview_tables import (
    migrate_postgresql,
    migrate_sqlite,
)


def _table_columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _index_names(conn, table_name):
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index' AND tbl_name = ?
        ORDER BY name
        """,
        (table_name,),
    )
    return {row[0] for row in rows}


def test_migration_functions_exist():
    assert callable(migrate_sqlite)
    assert callable(migrate_postgresql)


def test_sqlite_migration_creates_admin_interview_tables_and_indexes(tmp_path):
    db_path = tmp_path / "dashboard.db"
    sqlite3.connect(db_path).close()

    assert migrate_sqlite(str(db_path)) is True
    assert migrate_sqlite(str(db_path)) is True

    conn = sqlite3.connect(db_path)
    session_columns = _table_columns(conn, "admin_interview_sessions")
    message_columns = _table_columns(conn, "admin_interview_messages")

    assert {
        "exp_id",
        "admin_username",
        "agent_user_id",
        "agent_username",
        "run_id",
        "backend_mode",
        "llm_model",
        "llm_base_url",
        "persona_snapshot",
        "interests_snapshot_json",
        "memory_snapshot_json",
        "created_at",
        "updated_at",
    }.issubset(session_columns)
    assert {"session_id", "role", "content", "meta_json", "created_at"}.issubset(
        message_columns
    )

    assert {
        "ix_admin_interview_sessions_exp_id",
        "ix_admin_interview_sessions_admin_username",
        "ix_admin_interview_sessions_run_id",
    }.issubset(_index_names(conn, "admin_interview_sessions"))
    assert {"ix_admin_interview_messages_session_id"}.issubset(
        _index_names(conn, "admin_interview_messages")
    )


def test_sqlite_migration_backfills_additive_columns_on_existing_tables(tmp_path):
    db_path = tmp_path / "dashboard.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE admin_interview_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exp_id INTEGER NOT NULL,
            admin_username TEXT NOT NULL,
            agent_user_id INTEGER NOT NULL,
            agent_username TEXT NOT NULL,
            run_id VARCHAR(64)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO admin_interview_sessions (
            exp_id, admin_username, agent_user_id, agent_username, run_id
        ) VALUES (1, 'admin', 7, 'agent', 'legacy-run')
        """
    )
    conn.execute(
        """
        CREATE TABLE admin_interview_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO admin_interview_messages (session_id, role, content)
        VALUES (1, 'admin', 'hello')
        """
    )
    conn.commit()
    conn.close()

    assert migrate_sqlite(str(db_path)) is True

    conn = sqlite3.connect(db_path)
    session_columns = _table_columns(conn, "admin_interview_sessions")
    message_columns = _table_columns(conn, "admin_interview_messages")

    assert {
        "backend_mode",
        "llm_model",
        "llm_base_url",
        "persona_snapshot",
        "interests_snapshot_json",
        "memory_snapshot_json",
        "created_at",
        "updated_at",
    }.issubset(session_columns)
    assert {"meta_json", "created_at"}.issubset(message_columns)

    row = conn.execute(
        """
        SELECT backend_mode, created_at, updated_at
        FROM admin_interview_sessions
        WHERE id = 1
        """
    ).fetchone()
    assert row[0] == "agent_runtime"
    assert row[1] is not None
    assert row[2] is not None

    message_row = conn.execute(
        """
        SELECT meta_json, created_at
        FROM admin_interview_messages
        WHERE id = 1
        """
    ).fetchone()
    assert message_row[0] is None
    assert message_row[1] is not None


def test_startup_registers_admin_interview_table_migration_before_run_id_migration():
    source = Path("y_web/__init__.py").read_text()
    table_pos = source.index("add_admin_interview_tables")
    run_id_pos = source.index("add_admin_interview_run_id_text")
    assert table_pos < run_id_pos


def test_postgresql_schema_file_includes_admin_interview_tables():
    source = Path("data_schema/postgre_dashboard.sql").read_text()
    assert "CREATE TABLE admin_interview_sessions" in source
    assert "CREATE TABLE admin_interview_messages" in source
    assert "ix_admin_interview_sessions_run_id" in source
    assert "ix_admin_interview_messages_session_id" in source
