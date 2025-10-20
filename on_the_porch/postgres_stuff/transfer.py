import os
import pandas as pd
from sqlalchemy import create_engine
import os
import csv
from pathlib import Path


def _is_dictionary_file(file_path: Path) -> bool:
    lowercase_name = file_path.name.lower()
    return "dictionary" in lowercase_name


def _likely_dorchester(row: dict) -> bool:
    # Normalize keys to handle different schemas across files
    value_by_lower_key = {k.lower(): (v or "") for k, v in row.items()}

    # Candidate columns where Dorchester may appear (handle common misspellings like "dorchestor")
    neighborhood = value_by_lower_key.get("neighborhood", "")
    city = value_by_lower_key.get("city", "")
    # District may be under several headings across files
    district = value_by_lower_key.get("district", "") or value_by_lower_key.get("bpd district", "") or value_by_lower_key.get("bpd_district", "")

    text_fields = [neighborhood, city]
    for text in text_fields:
        if isinstance(text, str) and "dorchest" in text.lower():
            return True

    # District fallback: include Dorchester districts when neighborhood text is absent
    district_upper = str(district).upper()
    if district_upper in {"C11", "B3"}:
        return True
    return False


def filter_911_csvs_for_dorchester():
    base_dir = Path(__file__).resolve().parent
    input_dir = base_dir / "data" / "911_data"
    output_dir = base_dir / "data"

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in input_dir.glob("*.csv"):
        if _is_dictionary_file(csv_path):
            continue

        output_name = f"Dorchester_{csv_path.name}"
        output_path = output_dir / output_name

        with csv_path.open("r", newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in)
            fieldnames = reader.fieldnames or []
            # Skip files without headers
            if not fieldnames:
                continue

            with output_path.open("w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                writer.writeheader()
                for row in reader:
                    try:
                        if _likely_dorchester(row):
                            writer.writerow(row)
                    except Exception:
                        # Skip problematic rows to ensure robust processing across varied schemas
                        continue


if __name__ == "__main__":
    # Run filtering by default
    filter_911_csvs_for_dorchester()

    # Optional: set UPLOAD_TO_DB=1 to upload CSVs to Postgres after filtering
    if os.environ.get("UPLOAD_TO_DB") == "1":
        # --- CONFIGURATION ---
        PG_USER = "user1"
        PG_PASSWORD = "BbWTihWnsBHglVpeKK8XfQgEPDOcokZZ"
        PG_HOST = "dpg-d3g661u3jp1c73eg9v1g-a.render.com"
        PG_PORT = "5432"
        PG_DB = "crime_rate_h3u5"

        CSV_FOLDER = "./data"

        engine = create_engine(
            f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        )

        for filename in os.listdir(CSV_FOLDER):
            if filename.endswith(".csv"):
                file_path = os.path.join(CSV_FOLDER, filename)
                table_name = os.path.splitext(filename)[0]

                df = pd.read_csv(file_path)
                df.to_sql(table_name, engine, if_exists="replace", index=False)
                print(f"Uploaded {filename} to table {table_name}")

        print("All CSVs uploaded successfully!")
