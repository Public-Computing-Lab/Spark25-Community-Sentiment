import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any

import psycopg2
from psycopg2 import sql


def _get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set in environment (.env)", file=sys.stderr)
        sys.exit(1)
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
    except Exception as exc:
        print(f"DB connection failed: {exc}", file=sys.stderr)
        sys.exit(1)
    return conn


NUMERIC_TYPES = {
    "smallint",
    "integer",
    "bigint",
    "decimal",
    "numeric",
    "real",
    "double precision",
    "smallserial",
    "serial",
    "bigserial",
    "money",
}


def _is_text_type(data_type: str) -> bool:
    return data_type.strip().lower() == "text"


def _fetch_columns(conn, schema: str) -> Dict[str, List[Tuple[str, str]]]:
    query = (
        "SELECT table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema = %s "
        "ORDER BY table_name, ordinal_position"
    )
    table_to_cols: Dict[str, List[Tuple[str, str]]] = {}
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        for table_name, column_name, data_type in cur.fetchall():
            table_to_cols.setdefault(table_name, []).append((column_name, data_type))
    return table_to_cols


def _fetch_unique_values(
    conn,
    schema: str,
    table: str,
    column: str,
    limit: int,
) -> List[Any]:
    query = sql.SQL("""
        SELECT DISTINCT {col}
        FROM {schema}.{tbl}
        WHERE {col} IS NOT NULL
        LIMIT {lim}
    """).format(
        col=sql.Identifier(column),
        schema=sql.Identifier(schema),
        tbl=sql.Identifier(table),
        lim=sql.Literal(limit),
    )
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _is_numeric_type(data_type: str) -> bool:
    return data_type.strip().lower() in NUMERIC_TYPES


def generate_metadata_files(schema: str, output_dir: Path, unique_limit: int = 1000) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = _get_db_connection()
    try:
        tables = _fetch_columns(conn, schema)
        for table_name, cols in tables.items():
            table_meta: Dict[str, Any] = {
                "schema": schema,
                "table": table_name,
                "columns": {},
            }
            for col_name, data_type in cols:
                col_meta: Dict[str, Any] = {
                    "data_type": data_type,
                    "is_numeric": _is_numeric_type(data_type),
                }
                if _is_text_type(data_type):
                    try:
                        uniques = _fetch_unique_values(conn, schema, table_name, col_name, unique_limit)
                        col_meta["unique_values"] = uniques
                    except Exception as exc:  # noqa: BLE001
                        col_meta["unique_values_error"] = str(exc)
                table_meta["columns"][col_name] = col_meta

            out_path = output_dir / f"{table_name}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(table_meta, f, ensure_ascii=False, indent=2, default=str)
            print(f"Wrote {out_path}")
    finally:
        conn.close()


def main() -> None:
    schema = os.environ.get("PGSCHEMA", "public")
    # Default to sibling directory 'meta data' under on_the_porch
    default_output = Path(__file__).resolve().parents[1] / "meta data"
    output_dir = Path(os.environ.get("OUTPUT_DIR", str(default_output)))
    unique_limit = int(os.environ.get("UNIQUE_LIMIT", "1000"))
    generate_metadata_files(schema=schema, output_dir=output_dir, unique_limit=unique_limit)


if __name__ == "__main__":
    main()


