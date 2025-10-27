import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

import psycopg2


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


def _fetch_tables(conn, schema: str) -> List[str]:
    query = (
        "SELECT table_name "
        "FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    )
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _build_catalog(tables: List[str]) -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    for table_name in tables:
        catalog.append(
            {
                "table": table_name,
                "description": "TBD",
                "metadata_file": f"{table_name}.json",
            }
        )
    return catalog


def generate_catalog(schema: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_db_connection()
    try:
        tables = _fetch_tables(conn, schema)
    finally:
        conn.close()

    catalog = _build_catalog(tables)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"Wrote {output_path}")


def main() -> None:
    schema = os.environ.get("PGSCHEMA", "public")
    default_output = Path(__file__).resolve().parents[1] / "meta data" / "tables_catalog.json"
    output_path = Path(os.environ.get("OUTPUT_FILE", str(default_output)))
    generate_catalog(schema=schema, output_path=output_path)


if __name__ == "__main__":
    main()


