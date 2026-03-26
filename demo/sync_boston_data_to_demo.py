#!/usr/bin/env python3
"""
Run the existing Boston data syncer against the demo MySQL database
and sync only the 911/crime + 311 datasets into sentiment_demo.

Usage:
    python3 demo/sync_boston_data_to_demo.py

Optional:
    python3 demo/sync_boston_data_to_demo.py --full
"""

import os
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Force the syncer to use the demo DB
os.environ["MYSQL_HOST"] = "localhost"
os.environ["MYSQL_PORT"] = "3306"
os.environ["MYSQL_USER"] = "demo_user"
os.environ["MYSQL_PASSWORD"] = "demo_pass"
os.environ["MYSQL_DB"] = "sentiment_demo"

from on_the_porch.data_ingestion.boston_data_sync.boston_data_sync import BostonDataSyncer


TARGET_DATASETS = {
    "crime_incident_reports",   # 911/crime data
    "311_service_requests",     # 311 data
}


def main():
    parser = argparse.ArgumentParser(
        description="Sync Boston 311 and 911 data into sentiment_demo"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Do a full sync instead of incremental sync",
    )
    args = parser.parse_args()

    print("Using demo DB connection:")
    print(f"  MYSQL_HOST={os.environ['MYSQL_HOST']}")
    print(f"  MYSQL_PORT={os.environ['MYSQL_PORT']}")
    print(f"  MYSQL_USER={os.environ['MYSQL_USER']}")
    print(f"  MYSQL_DB={os.environ['MYSQL_DB']}")

    with BostonDataSyncer() as syncer:
        matched = [
            dataset
            for dataset in syncer.datasets_config["datasets"]
            if dataset.get("name") in TARGET_DATASETS
        ]

        if not matched:
            raise RuntimeError(
                "No matching datasets found in boston_datasets_config.json "
                "for crime_incident_reports or 311_service_requests."
            )

        print("\nDatasets to sync:")
        for dataset in matched:
            print(f"  - {dataset['name']} -> {dataset['table_name']}")

        for dataset in matched:
            print(f"\n=== Syncing {dataset['name']} ===")
            syncer.sync_dataset(dataset, incremental=not args.full)

    print("\nDone.")


if __name__ == "__main__":
    main()
