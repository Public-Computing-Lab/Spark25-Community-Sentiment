#!/usr/bin/env python3
"""Sync live Boston 311 and crime data into the demo MySQL database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ["MYSQL_HOST"] = "127.0.0.1"
os.environ["MYSQL_PORT"] = "3306"
os.environ["MYSQL_USER"] = "demo_user"
os.environ["MYSQL_PASSWORD"] = "demo_pass"
os.environ["MYSQL_DB"] = "sentiment_demo"

from on_the_porch.data_ingestion.boston_data_sync.boston_data_sync import BostonDataSyncer

TARGET_DATASETS = {
    "crime_incident_reports",
    "311_service_requests",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Boston 311 and crime data into sentiment_demo")
    parser.add_argument("--full", action="store_true", help="Run a full sync instead of incremental sync")
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
                "No matching datasets found in the Boston dataset config for crime_incident_reports or 311_service_requests."
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
