"""
Ensure PostgreSQL dashboard default configuration tables are populated.

This migration backfills missing canonical rows used by population configuration
UI and agent generation. It is intentionally non-destructive:
- existing PostgreSQL rows are preserved
- only missing canonical rows are inserted

Canonical rows are loaded from the bundled SQLite dashboard template:
  data_schema/database_dashboard.db
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any

try:
    import psycopg2
    from psycopg2 import sql

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]


CANONICAL_TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec("content_recsys", ("name", "value"), ("name",)),
    TableSpec("follow_recsys", ("name", "value"), ("name",)),
    TableSpec("leanings", ("leaning",), ("leaning",)),
    TableSpec("toxicity_levels", ("toxicity_level",), ("toxicity_level",)),
    TableSpec("education", ("education_level",), ("education_level",)),
    TableSpec("languages", ("language",), ("language",)),
    TableSpec("nationalities", ("nationality",), ("nationality",)),
    TableSpec("age_classes", ("name", "age_start", "age_end"), ("name",)),
    TableSpec("professions", ("profession", "background"), ("profession",)),
    TableSpec("activity_profiles", ("name", "hours"), ("name",)),
)


def _normalize_key(parts: tuple[Any, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in parts:
        if value is None:
            normalized.append("")
        else:
            normalized.append(str(value).strip())
    return tuple(normalized)


def _tuple_by_columns(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row[c] for c in columns)


def _build_key_from_row(row: dict[str, Any], key_columns: tuple[str, ...]) -> tuple[str, ...]:
    return _normalize_key(tuple(row[c] for c in key_columns))


def _sqlite_template_path() -> str:
    # Resolve relative to repository layout:
    # y_web/migrations/ensure_dashboard_default_config.py -> YSocial/data_schema
    migrations_dir = os.path.dirname(os.path.abspath(__file__))
    ysocial_root = os.path.dirname(os.path.dirname(migrations_dir))
    return os.path.join(ysocial_root, "data_schema", "database_dashboard.db")


def load_canonical_defaults(sqlite_path: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Load canonical defaults from bundled SQLite dashboard database.

    Args:
        sqlite_path: Optional explicit path to canonical SQLite DB

    Returns:
        dict keyed by table name containing ordered list of row dicts
    """
    db_path = sqlite_path or _sqlite_template_path()
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Canonical SQLite database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    canonical: dict[str, list[dict[str, Any]]] = {}
    try:
        for spec in CANONICAL_TABLE_SPECS:
            col_sql = ", ".join(spec.columns)
            cur.execute(f"SELECT {col_sql} FROM {spec.name}")
            rows = [dict(r) for r in cur.fetchall()]
            canonical[spec.name] = rows
        return canonical
    finally:
        conn.close()


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def _fetch_pg_rows(cursor, spec: TableSpec) -> list[dict[str, Any]]:
    query = sql.SQL("SELECT {cols} FROM {table}").format(
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in spec.columns),
        table=sql.Identifier(spec.name),
    )
    cursor.execute(query)
    return [dict(zip(spec.columns, row)) for row in cursor.fetchall()]


def drift_report_postgresql(
    host: str,
    port: str,
    database: str,
    user: str,
    password: str,
    sqlite_path: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Compare PostgreSQL dashboard config tables with canonical defaults.

    Returns a per-table drift report that includes missing canonical keys and
    keys with non-canonical values for matching natural keys.
    """
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError("psycopg2 not available")

    canonical = load_canonical_defaults(sqlite_path)
    conn = psycopg2.connect(
        host=host, port=port, database=database, user=user, password=password
    )
    cur = conn.cursor()

    report: dict[str, dict[str, Any]] = {}
    try:
        for spec in CANONICAL_TABLE_SPECS:
            canonical_by_key = {
                _build_key_from_row(row, spec.key_columns): row
                for row in canonical[spec.name]
            }

            table_report: dict[str, Any] = {
                "table_exists": _table_exists(cur, spec.name),
                "canonical_count": len(canonical_by_key),
                "postgres_count": 0,
                "missing_canonical_keys": [],
                "extra_postgres_keys": [],
                "mismatched_rows": [],
            }
            if not table_report["table_exists"]:
                report[spec.name] = table_report
                continue

            pg_rows = _fetch_pg_rows(cur, spec)
            table_report["postgres_count"] = len(pg_rows)
            postgres_by_key = {
                _build_key_from_row(row, spec.key_columns): row for row in pg_rows
            }

            canonical_keys = set(canonical_by_key.keys())
            postgres_keys = set(postgres_by_key.keys())

            missing = sorted(canonical_keys - postgres_keys)
            extra = sorted(postgres_keys - canonical_keys)

            table_report["missing_canonical_keys"] = [list(k) for k in missing]
            table_report["extra_postgres_keys"] = [list(k) for k in extra]

            mismatches: list[dict[str, Any]] = []
            for key in sorted(canonical_keys & postgres_keys):
                canonical_tuple = _tuple_by_columns(canonical_by_key[key], spec.columns)
                postgres_tuple = _tuple_by_columns(postgres_by_key[key], spec.columns)
                if canonical_tuple != postgres_tuple:
                    mismatches.append(
                        {
                            "key": list(key),
                            "canonical": list(canonical_tuple),
                            "postgres": list(postgres_tuple),
                        }
                    )
            table_report["mismatched_rows"] = mismatches
            report[spec.name] = table_report
    finally:
        conn.close()

    return report


def migrate_postgresql(
    host: str,
    port: str,
    database: str,
    user: str,
    password: str,
    sqlite_path: str | None = None,
) -> bool:
    """
    Backfill missing canonical dashboard config rows in PostgreSQL.

    This migration inserts missing rows only; existing rows are preserved.
    """
    if not PSYCOPG2_AVAILABLE:
        print("✗ psycopg2 not available. Cannot migrate PostgreSQL database.")
        return False

    try:
        canonical = load_canonical_defaults(sqlite_path)
    except Exception as e:
        print(f"✗ Failed to load canonical defaults: {e}")
        return False

    try:
        conn = psycopg2.connect(
            host=host, port=port, database=database, user=user, password=password
        )
        cur = conn.cursor()

        total_inserted = 0
        for spec in CANONICAL_TABLE_SPECS:
            if not _table_exists(cur, spec.name):
                print(f"○ Table not found, skipping default backfill: {spec.name}")
                continue

            existing_rows = _fetch_pg_rows(cur, spec)
            existing_keys = {
                _build_key_from_row(row, spec.key_columns) for row in existing_rows
            }

            inserted = 0
            for row in canonical[spec.name]:
                key = _build_key_from_row(row, spec.key_columns)
                if key in existing_keys:
                    continue

                insert_query = sql.SQL("INSERT INTO {table} ({cols}) VALUES ({vals})").format(
                    table=sql.Identifier(spec.name),
                    cols=sql.SQL(", ").join(sql.Identifier(c) for c in spec.columns),
                    vals=sql.SQL(", ").join(sql.Placeholder() for _ in spec.columns),
                )
                values = _tuple_by_columns(row, spec.columns)
                cur.execute(insert_query, values)
                existing_keys.add(key)
                inserted += 1

            total_inserted += inserted
            if inserted:
                print(f"✓ Backfilled {inserted} canonical rows in {spec.name}")
            else:
                print(f"○ No canonical rows missing in {spec.name}")

        conn.commit()
        conn.close()
        print(f"✓ Dashboard default configuration backfill complete ({total_inserted} rows inserted)")
        return True

    except Exception as e:
        print(f"✗ Error migrating PostgreSQL dashboard defaults: {e}")
        return False
