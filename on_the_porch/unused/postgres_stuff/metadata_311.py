import json
import os
from datetime import datetime

import pandas as pd


def generate_metadata(
    csv_path: str,
    output_dir: str,
    table_name: str | None = None,
    sample_rows: int = 100_000,
    categorical_unique_cap: int = 50,
) -> str:
    """
    Generate simple metadata JSON for a CSV using a sampled read for efficiency.

    - Detects basic dtypes from pandas
    - Treats object-typed columns (or columns with few uniques) as categorical
    - Captures up to `categorical_unique_cap` unique values for categorical cols

    Returns the path to the written JSON file.
    """

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    os.makedirs(output_dir, exist_ok=True)

    inferred_table_name = (
        table_name if table_name else os.path.splitext(os.path.basename(csv_path))[0]
    )

    # Read a sample for performance on very large files
    df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)

    metadata: dict[str, object] = {
        "table_name": inferred_table_name,
        "source_file": os.path.basename(csv_path),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "row_count_sampled": int(len(df)),
        "columns": [],
    }

    num_rows = len(df)

    # Heuristic: consider column categorical if dtype is object
    # or if unique values are very small relative to sampled rows
    for column_name in df.columns:
        series = df[column_name]
        dtype_str = str(series.dtype)
        nunique = int(series.nunique(dropna=True))

        # Categorical heuristics kept simple as requested
        is_object_type = dtype_str == "object"
        is_few_uniques = nunique <= max(10, min(categorical_unique_cap, int(0.01 * max(1, num_rows))))
        is_categorical = bool(is_object_type or is_few_uniques)

        column_info: dict[str, object] = {
            "name": column_name,
            "dtype": dtype_str,
            "description": f"Placeholder description for '{column_name}'.",
            "is_categorical": is_categorical,
        }

        if is_categorical:
            # Collect up to categorical_unique_cap unique values (by frequency)
            top_unique = (
                series.dropna()
                .astype(str)
                .value_counts()
                .head(categorical_unique_cap)
                .index.tolist()
            )
            column_info["unique_values"] = top_unique

        metadata["columns"].append(column_info)

    output_path = os.path.join(output_dir, f"{inferred_table_name}_metadata.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return output_path


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "data", "Dorchester_311.csv")
    output_dir = os.path.join(base_dir, "meta data")

    output_json = generate_metadata(
        csv_path=csv_path,
        output_dir=output_dir,
        table_name="Dorchester_311",
        sample_rows=100_000,
        categorical_unique_cap=50,
    )

    print(f"Metadata written to: {output_json}")


if __name__ == "__main__":
    main()


