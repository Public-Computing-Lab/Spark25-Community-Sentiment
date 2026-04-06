#!/usr/bin/env python3
"""
Generate metadata files from live MySQL database.

This script connects to the MySQL database and generates metadata JSON files
for the Boston data sync tables. It extracts:
- Column names and data types
- Unique values for non-numeric columns (up to 150 per column)
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    print("ERROR: pymysql not installed. Run: pip install pymysql")
    sys.exit(1)


# Default MySQL connection settings (can be overridden by environment variables)
MYSQL_CONFIG = {
    'host': os.getenv("MYSQL_HOST", "127.0.0.1"),
    'port': int(os.getenv("MYSQL_PORT", "3306")),
    'user': os.getenv("MYSQL_USER", "root"),
    'password': os.getenv("MYSQL_PASSWORD", ""),
    'database': os.getenv("MYSQL_DB", "rethink_ai_boston"),
    'charset': 'utf8mb4',
}

# Tables to generate metadata for
TARGET_TABLES = ["crime_incident_reports", "service_requests_311", "shootings"]

# Heuristic: which MySQL types should we treat as numeric?
NUMERIC_PREFIXES = (
    "int", "tinyint", "smallint", "mediumint", "bigint",
    "decimal", "numeric", "float", "double", "real",
)


def _is_numeric_type(dtype: str) -> bool:
    """Check if a MySQL data type is numeric."""
    dt = dtype.strip().lower().strip("`")
    first = dt.split()[0]
    return any(first.startswith(prefix) for prefix in NUMERIC_PREFIXES)


def _get_mysql_connection():
    """Get MySQL connection."""
    try:
        conn = pymysql.connect(
            **MYSQL_CONFIG,
            cursorclass=DictCursor,
            autocommit=False
        )
        print(f"Connected to MySQL: {MYSQL_CONFIG['database']}")
        return conn
    except Exception as e:
        print(f"ERROR: MySQL connection failed: {e}")
        raise


def get_table_schema(conn, table_name: str) -> List[Tuple[str, str]]:
    """
    Get column names and data types for a table.
    Returns list of (column_name, data_type) tuples.
    """
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """, (table_name,))
    
    columns = []
    for row in cursor.fetchall():
        col_name = row['COLUMN_NAME']
        # Use COLUMN_TYPE which includes size/precision (e.g., "varchar(255)")
        # Fall back to DATA_TYPE if COLUMN_TYPE is not available
        col_type = row.get('COLUMN_TYPE') or row['DATA_TYPE']
        columns.append((col_name, col_type))
    
    return columns


def fetch_unique_values(conn, table_name: str, column_name: str, limit: int = 150) -> List[str]:
    """
    Fetch up to `limit` distinct non-null values from a column.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            SELECT DISTINCT `{column_name}`
            FROM `{table_name}`
            WHERE `{column_name}` IS NOT NULL
            ORDER BY `{column_name}`
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        # Handle both DictCursor and regular cursor
        if rows and isinstance(rows[0], dict):
            return [str(row[column_name]) for row in rows]
        else:
            return [str(row[0]) for row in rows]
    except Exception as e:
        print(f"   WARNING: Error fetching unique values for {table_name}.{column_name}: {e}")
        return []


def generate_metadata_for_table(conn, table_name: str) -> Dict:
    """
    Generate metadata for a single table.
    """
    print(f"\nProcessing table: {table_name}")
    
    # Check if table exists
    cursor = conn.cursor()
    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
    if not cursor.fetchone():
        print(f"   WARNING: Table '{table_name}' does not exist, skipping")
        return None
    
    # Get schema
    columns = get_table_schema(conn, table_name)
    if not columns:
        print(f"   WARNING: No columns found for '{table_name}'")
        return None
    
    print(f"   Found {len(columns)} columns")
    
    # Build metadata
    meta = {
        "schema": "mysql",
        "table": table_name,
        "columns": {},
    }
    
    # Process each column
    for col_name, dtype in columns:
        print(f"   Processing column: {col_name} ({dtype})")
        col_meta = {
            "data_type": dtype,
            "is_numeric": _is_numeric_type(dtype),
        }
        
        # For non-numeric columns, fetch unique values
        if not col_meta["is_numeric"]:
            unique_values = fetch_unique_values(conn, table_name, col_name, limit=150)
            if unique_values:
                col_meta["unique_values"] = unique_values
                print(f"      Found {len(unique_values)} unique values")
        
        meta["columns"][col_name] = col_meta
    
    return meta


def write_metadata_file(metadata: Dict, output_dir: Path):
    """Write metadata to JSON file."""
    table_name = metadata["table"]
    output_path = output_dir / f"{table_name}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"Wrote: {output_path}")


def main():
    """Main entry point."""
    print("="*60)
    print("Generating MySQL Metadata from Live Database")
    print("="*60)
    
    # Connect to database
    conn = None
    try:
        conn = _get_mysql_connection()
        
        # Output directory (same as script)
        output_dir = Path(__file__).resolve().parent
        print(f"Output directory: {output_dir}")
        
        # Generate metadata for each table
        generated_count = 0
        for table_name in TARGET_TABLES:
            try:
                metadata = generate_metadata_for_table(conn, table_name)
                if metadata:
                    write_metadata_file(metadata, output_dir)
                    generated_count += 1
            except Exception as e:
                print(f"ERROR: Error processing {table_name}: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "="*60)
        print(f"Generated metadata for {generated_count} table(s)")
        print("="*60)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()

