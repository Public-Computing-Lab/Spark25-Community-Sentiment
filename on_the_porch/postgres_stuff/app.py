import os
import re
from pathlib import Path
from typing import List

import pandas as pd
from sqlalchemy import create_engine


def _get_project_data_dir() -> Path:
    """Return the absolute path to the project's data directory.

    This file lives in <project_root>/postgres_stuff/app.py, so data dir is <project_root>/data.
    """
    project_root = Path(__file__).resolve().parents[1]
    return project_root / "data"


def _find_all_csvs(data_dir: Path) -> List[Path]:
    """Recursively find all CSV files under data_dir."""
    return sorted(data_dir.rglob("*.csv"))


def _make_table_name(csv_path: Path, data_dir: Path) -> str:
    """Create a safe Postgres table name from the CSV path relative to data_dir.

    Example: data/911_data/Boston_Arrests.csv -> 911_data_boston_arrests
    """
    relative = csv_path.relative_to(data_dir)
    name_without_ext = relative.with_suffix("")
    raw = "_".join(name_without_ext.parts)
    table = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_")
    if not table:
        table = "table"
    if table[0].isdigit():
        table = f"t_{table}"
    return table.lower()[:63]  # Postgres identifier limit


def _get_engine_from_env():
    """Build a SQLAlchemy engine from env vars.

    Priority:
      1) DATABASE_URL (Render default)
      2) PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE
    """
    return create_engine(f"postgresql://dorchester_db_user:6CiTHuq3z1aC8gSokVr560LX7qiF7CtW@dpg-d3pcedggjchc73aff580-a.ohio-postgres.render.com/dorchester_db")

def upload_all_csvs() -> None:
    data_dir = _get_project_data_dir()
    if not data_dir.exists():
        print(f"❌ Data directory not found: {data_dir}")
        return

    csv_files = _find_all_csvs(data_dir)
    if not csv_files:
        print(f"No CSV files found under {data_dir}")
        return

    engine = _get_engine_from_env()

    print(f"Found {len(csv_files)} CSV file(s). Uploading to Postgres...")
    for csv_path in csv_files:
        table_name = _make_table_name(csv_path, data_dir)
        print(f"→ {csv_path.relative_to(data_dir)} -> table '{table_name}'")
        try:
            # Try UTF-8 first, then fallback to latin1 if needed
            try:
                df = pd.read_csv(csv_path)
            except UnicodeDecodeError:
                df = pd.read_csv(csv_path, encoding="latin1")

            df.to_sql(table_name, engine, if_exists="replace", index=False)
            print(f"   ✅ Uploaded '{table_name}' ({len(df)} rows)")
        except Exception as exc:
            print(f"   ❌ Failed to upload '{table_name}': {exc}")

    print("🎉 All done.")


if __name__ == "main" or __name__ == "__main__":
    upload_all_csvs()
