import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import pymysql  # type: ignore
except Exception:  # pragma: no cover
    pymysql = None  # type: ignore


# Path to the large MySQL dump
DUMP_PATH = Path("goebel_iad1-mysql-e2-17b_dreamhost_com.sql")

# Only generate metadata for these tables
TARGET_TABLES = {"crime_incident_reports", "service_requests_311", "shootings"}


# Heuristic: which MySQL types should we treat as numeric?
NUMERIC_PREFIXES = (
    "int",
    "tinyint",
    "smallint",
    "mediumint",
    "bigint",
    "decimal",
    "numeric",
    "float",
    "double",
    "real",
)


def _is_numeric_type(dtype: str) -> bool:
    """
    Very simple check: look at the leading token of the type.
    Examples:
        int(11) -> int
        bigint(20) unsigned -> bigint
    """
    dt = dtype.strip().lower()
    # Strip any leading/trailing punctuation
    dt = dt.strip("`")
    # Grab the first word, dropping size/params
    first = dt.split()[0]
    for prefix in NUMERIC_PREFIXES:
        if first.startswith(prefix):
            return True
    return False


def _get_mysql_connection():
    """
    Connect to the live MySQL database to fetch unique values.
    Uses environment variables:
      MYSQL_HOST (default: localhost)
      MYSQL_PORT (default: 3306)
      MYSQL_USER (required)
      MYSQL_PASSWORD (optional)
      MYSQL_DB (required)
    """
    if pymysql is None:
        raise SystemExit("pymysql not installed. Run: pip install pymysql")

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD", "")
    db = os.getenv("MYSQL_DB")

    if not user or not db:
        raise SystemExit("MYSQL_USER and MYSQL_DB must be set in the environment.")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )


def _fetch_unique_values(conn, table: str, column: str, limit: int = 150):
    """
    Fetch up to `limit` distinct non-null values from the given column.
    """
    sql = f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL LIMIT %s"
    with conn.cursor() as cur:
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    return [r[0] for r in rows]


CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+`(?P<table>\w+)`", re.IGNORECASE
)
COLUMN_DEF_RE = re.compile(
    r"^\s*`(?P<col>\w+)`\s+(?P<dtype>[^,\s]+)", re.IGNORECASE
)


def parse_create_table_blocks(
    dump_path: Path,
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Stream the SQL dump and extract column definitions for target tables.
    Returns a mapping: table_name -> list of (column_name, data_type) tuples.
    """
    tables: Dict[str, List[Tuple[str, str]]] = {}
    current_table: str | None = None

    with dump_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if current_table is None:
                # Look for a CREATE TABLE for one of our target tables
                m = CREATE_TABLE_RE.search(line)
                if not m:
                    continue
                table_name = m.group("table")
                if table_name not in TARGET_TABLES:
                    # Skip tables we don't care about
                    current_table = None
                    continue
                current_table = table_name
                tables.setdefault(current_table, [])
                continue

            # We are inside a CREATE TABLE block for a target table
            stripped = line.strip()

            # End of CREATE TABLE statement
            if stripped.startswith(")") and ("ENGINE=" in stripped or stripped.endswith(";")):
                current_table = None
                continue

            # Skip constraint / key lines
            upper = stripped.upper()
            if upper.startswith(("PRIMARY KEY", "UNIQUE KEY", "KEY ", "CONSTRAINT", "FOREIGN KEY")):
                continue

            # Try to parse a column definition
            m_col = COLUMN_DEF_RE.match(line)
            if not m_col:
                continue
            col_name = m_col.group("col")
            dtype = m_col.group("dtype")
            tables[current_table].append((col_name, dtype))

    return tables


def _parse_values_segment(values_sql: str) -> List[List[str]]:
    """
    Very small parser for the VALUES(...) segment of an INSERT statement.
    Returns a list of rows, each row is a list of raw string values (or 'NULL').
    """
    rows: List[List[str]] = []
    in_row = False
    in_string = False
    escape = False
    current_row: List[str] = []
    current_value_chars: List[str] = []

    for ch in values_sql:
        if not in_row:
            if ch == "(":
                in_row = True
                current_row = []
                current_value_chars = []
            continue

        if in_string:
            if escape:
                current_value_chars.append(ch)
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_string = False
            else:
                current_value_chars.append(ch)
            continue

        # Not in string
        if ch == "'":
            in_string = True
        elif ch == ",":
            value = "".join(current_value_chars).strip()
            current_row.append(value)
            current_value_chars = []
        elif ch == ")":
            value = "".join(current_value_chars).strip()
            if value:
                current_row.append(value)
            rows.append(current_row)
            in_row = False
            current_row = []
            current_value_chars = []
        else:
            current_value_chars.append(ch)

    return rows


def collect_unique_values_from_dump(
    dump_path: Path,
    tables: Dict[str, List[Tuple[str, str]]],
    max_uniques: int = 150,
) -> Dict[str, Dict[str, List[str]]]:
    """
    Scan the SQL dump for INSERT statements and collect up to `max_uniques`
    distinct non-null values per non-numeric column, per table.
    """
    # Determine which columns are non-numeric and their positions
    non_numeric_info: Dict[str, List[Tuple[int, str]]] = {}
    for table_name, cols in tables.items():
        positions: List[Tuple[int, str]] = []
        for idx, (col_name, dtype) in enumerate(cols):
            if not _is_numeric_type(dtype):
                positions.append((idx, col_name))
        if positions:
            non_numeric_info[table_name] = positions

    # Prepare storage for uniques
    uniques: Dict[str, Dict[str, set]] = {
        t: {col_name: set() for _, col_name in positions}
        for t, positions in non_numeric_info.items()
    }

    # If nothing to collect, return early
    if not uniques:
        return {}

    # Match forms like:
    #   INSERT INTO `bos311_data` VALUES ...
    #   INSERT INTO `bos311_data` (`col1`, `col2`, ...) VALUES ...
    #   INSERT INTO bos311_data VALUES ...
    #   INSERT INTO bos311_data (`col1`, `col2`) VALUES ...
    insert_re = re.compile(
        r"INSERT\s+INTO\s+`?(?P<table>\w+)`?(?:\s*\([^)]*\))?\s+VALUES",
        re.IGNORECASE,
    )

    with dump_path.open("r", encoding="utf-8", errors="ignore") as f:
        buffer = ""
        current_table: str | None = None

        for line in f:
            if current_table is None:
                m = insert_re.search(line)
                if not m:
                    continue
                table_name = m.group("table")
                if table_name not in non_numeric_info:
                    # Not one of the tables we care about
                    current_table = None
                    continue
                current_table = table_name
                buffer = line
            else:
                buffer += line

            # End of this INSERT statement
            if ";" in line and current_table is not None:
                upper = buffer.upper()
                idx = upper.find("VALUES")
                if idx == -1:
                    buffer = ""
                    current_table = None
                    continue

                values_part = buffer[idx + len("VALUES") :].rsplit(";", 1)[0].strip()
                rows = _parse_values_segment(values_part)

                # Map values into columns
                positions = non_numeric_info[current_table]
                for row in rows:
                    for pos, col_name in positions:
                        if len(uniques[current_table][col_name]) >= max_uniques:
                            continue
                        if pos >= len(row):
                            continue
                        raw_val = row[pos]
                        if not raw_val or raw_val.upper() == "NULL":
                            continue
                        uniques[current_table][col_name].add(raw_val)

                buffer = ""
                current_table = None

    # Convert sets to lists
    result: Dict[str, Dict[str, List[str]]] = {}
    for table_name, col_dict in uniques.items():
        result[table_name] = {
            col_name: sorted(values) for col_name, values in col_dict.items()
        }
    return result


def write_metadata_files(
    tables: Dict[str, List[Tuple[str, str]]],
    output_dir: Path,
    schema_name: str = "mysql",
) -> None:
    """
    Write one JSON metadata file per table, similar to files in 'meta data'.
    For non-numeric columns, store up to 150 unique values, taken directly
    from the MySQL dump (no live DB connection required).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    uniques_by_table = collect_unique_values_from_dump(DUMP_PATH, tables, max_uniques=150)

    for table_name, cols in tables.items():
        meta = {
            "schema": schema_name,
            "table": table_name,
            "columns": {},
        }
        table_uniques = uniques_by_table.get(table_name, {})
        for col_name, dtype in cols:
            col_meta = {
                "data_type": dtype,
                "is_numeric": _is_numeric_type(dtype),
            }
            if not col_meta["is_numeric"]:
                uniques = table_uniques.get(col_name, [])
                if uniques:
                    col_meta["unique_values"] = uniques[:150]

            meta["columns"][col_name] = col_meta

        out_path = output_dir / f"{table_name}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_path}")


def main() -> None:
    if not DUMP_PATH.exists():
        raise SystemExit(f"SQL dump not found: {DUMP_PATH}")

    tables = parse_create_table_blocks(DUMP_PATH)
    if not tables:
        print("No matching tables found in dump for targets:", ", ".join(sorted(TARGET_TABLES)))
        return

    # Write JSON files into the same directory as this script
    output_dir = Path(__file__).resolve().parent
    write_metadata_files(tables, output_dir)


if __name__ == "__main__":
    main()


