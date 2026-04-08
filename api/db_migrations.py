from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Set

import mysql.connector


IGNORABLE_ERROR_CODES = {
    1060,  # duplicate column
    1061,  # duplicate key name
    1091,  # can't drop/check that column/key exists
}


def _iter_sql_statements(script: str) -> Iterable[str]:
    for raw_statement in script.split(";"):
        statement = raw_statement.strip()
        if statement:
            yield statement


def _ensure_schema_migrations_table(conn) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.commit()
    finally:
        cursor.close()


def _get_applied_versions(conn) -> Set[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()


def _apply_migration(conn, version: str, sql_path: Path) -> None:
    script = sql_path.read_text(encoding="utf-8")
    cursor = conn.cursor()
    try:
        for statement in _iter_sql_statements(script):
            try:
                cursor.execute(statement)
            except mysql.connector.Error as exc:
                if exc.errno in IGNORABLE_ERROR_CODES:
                    continue
                raise
        cursor.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (version,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def run_migrations(connection_factory: Callable[[], object], migrations_dir: Path | None = None) -> None:
    migrations_path = migrations_dir or (Path(__file__).resolve().parent / "migrations")
    if not migrations_path.exists():
        return

    conn = connection_factory()
    try:
        _ensure_schema_migrations_table(conn)
        applied_versions = _get_applied_versions(conn)

        migration_files = sorted(path for path in migrations_path.glob("*.sql") if path.is_file())
        for sql_path in migration_files:
            version = sql_path.name
            if version in applied_versions:
                continue
            print(f"Applying migration {version}...")
            _apply_migration(conn, version, sql_path)
            print(f"Applied migration {version}")
    finally:
        conn.close()
