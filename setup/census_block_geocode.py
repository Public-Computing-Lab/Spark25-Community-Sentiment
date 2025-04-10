#!/usr/bin/env python3
import mysql.connector
import requests
import time
import logging
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional

#
# Updates any table w/ lat long to include a column for census block geo_id (or FIPS).
# Once done, this can be used to link whatever census demographic info you want based on
# census block (or block group, or track, as FIPS is nested)
#
# Set .env w/ database info
# Set TABLE and FIELD below for what to update
# Batch size and max should be adjusted to expected table size.
#

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", filename="fips_update.log")

load_dotenv()

# Database configuration - replace with your actual credentials
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

# FCC API endpoint
FCC_API_URL = "https://geo.fcc.gov/api/census/block/find"

# options
TABLE = "bos311_data"
FIELD = "census_block_geo_id"
# batch request/update, max set to run through all bos311 records
BATCH_SIZE = 1000
BATCH_MAX = 1875


def connect_to_database() -> mysql.connector.connection.MySQLConnection:
    """Establish connection to MySQL database."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        logging.info("Successfully connected to MySQL database")
        return connection
    except mysql.connector.Error as err:
        logging.error(f"Database connection error: {err}")
        raise


def get_records_without_fips(connection: mysql.connector.connection.MySQLConnection, batch_size: int = 100) -> list:
    """Get records that need FIPS data updated."""
    cursor = connection.cursor(dictionary=True)

    # Query for records without FIPS data or with empty FIPS
    # Adjust the condition as needed
    query = f"""
    SELECT id, latitude, longitude
    FROM {TABLE}
    WHERE ({FIELD} IS NULL OR {FIELD} = '')
    AND latitude IS NOT NULL
    AND longitude IS NOT NULL
    LIMIT %s
    """

    cursor.execute(query, (batch_size,))
    records = cursor.fetchall()
    cursor.close()

    logging.info(f"Retrieved {len(records)} records that need FIPS data")
    return records


def get_fips_from_fcc_api(latitude: float, longitude: float) -> Optional[str]:
    """Query the FCC API and extract the FIPS value from the Block object."""
    params = {"format": "json", "latitude": latitude, "longitude": longitude}

    try:
        response = requests.get(FCC_API_URL, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors

        data = response.json()

        # Extract the FIPS value from the nested Block object
        # Based on the example JSON structure: {"Block": {"FIPS": "250251010016008", ...}, ...}
        if "Block" in data and isinstance(data["Block"], dict) and "FIPS" in data["Block"]:
            return data["Block"]["FIPS"]
        else:
            logging.warning(f"No Block FIPS data found in response for coordinates ({latitude}, {longitude})")
            logging.debug(f"Response data: {data}")
            return None

    except requests.RequestException as e:
        logging.error(f"API request error for coordinates ({latitude}, {longitude}): {e}")
        return None
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Error processing API response for coordinates ({latitude}, {longitude}): {e}")
        logging.debug(f"Response data: {str(data) if 'data' in locals() else 'No data'}")
        return None


def update_fips_in_database(connection: mysql.connector.connection.MySQLConnection, record_id: int, fips: str) -> bool:
    """Update the FIPS field for a specific record."""
    cursor = connection.cursor()

    try:
        update_query = f"""
        UPDATE {TABLE}
        SET {FIELD} = %s
        WHERE id = %s
        """

        cursor.execute(update_query, (fips, record_id))
        connection.commit()

        logging.info(f"Updated FIPS value for record ID {record_id}")
        return True

    except mysql.connector.Error as err:
        logging.error(f"Error updating FIPS for record ID {record_id}: {err}")
        connection.rollback()
        return False
    finally:
        cursor.close()


def process_batch(connection: mysql.connector.connection.MySQLConnection, batch_size: int = 100) -> int:
    """Process a batch of records, updating their FIPS values."""
    records = get_records_without_fips(connection, batch_size)

    if not records:
        logging.info("No records found that need FIPS data")
        return 0

    updated_count = 0

    for record in records:
        record_id = record["id"]
        latitude = record["latitude"]
        longitude = record["longitude"]

        # Skip records with missing coordinates
        if latitude is None or longitude is None:
            logging.warning(f"Record ID {record_id} has missing coordinates, skipping")
            continue

        # Get FIPS data from FCC API
        fips_value = get_fips_from_fcc_api(latitude, longitude)

        if fips_value:
            # Update the database with the FIPS value
            success = update_fips_in_database(connection, record_id, fips_value)
            if success:
                updated_count += 1

    return updated_count


def main():
    try:
        connection = connect_to_database()

        total_updated = 0

        for batch_num in range(BATCH_MAX):
            logging.info(f"Processing batch {batch_num + 1}")

            updated_count = process_batch(connection, BATCH_SIZE)
            total_updated += updated_count

            if updated_count == 0:
                # No more records to process
                break

            logging.info(f"Batch {batch_num + 1} completed: {updated_count} records updated")

        logging.info(f"Process completed: Total {total_updated} records updated")

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        if "connection" in locals() and connection.is_connected():
            connection.close()
            logging.info("Database connection closed")


if __name__ == "__main__":
    main()
