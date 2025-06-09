from flask import Flask, request, jsonify, g, session, Response, stream_with_context
import csv
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pathlib import Path
from typing import List, Union, Optional, Generator
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import datetime
import os
import re
import io
import uuid
import json
import decimal
from pydantic import BaseModel

from flask import Flask
from flask_cors import CORS

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).parent


# Configuration constants
class Config:
    API_VERSION = "API v 0.6"
    RETHINKAI_API_KEYS = os.getenv("RETHINKAI_API_KEYS").split(",")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL")
    GEMINI_CACHE_TTL = float(os.getenv("GEMINI_CACHE_TTL", "0.125"))
    HOST = os.getenv("API_HOST", "127.0.0.1")
    PORT = os.getenv("API_PORT", "8888")
    DATASTORE_PATH = BASE_DIR / Path(
        os.getenv("DATASTORE_PATH", "./datastore").lstrip("./")
    )
    PROMPTS_PATH = BASE_DIR / Path(os.getenv("PROMPTS_PATH", "./prompts").lstrip("./"))
    ALLOWED_EXTENSIONS = {"csv", "txt"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "rethinkAI2025!")
    FLASK_SESSION_COOKIE_SECURE = (
        os.getenv("FLASK_SESSION_COOKIE_SECURE", "False").lower() == "true"
    )

    # Database configuration
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }


# Initialize GenAI client
genai_client = genai.Client(api_key=Config.GEMINI_API_KEY)

# Create connection pool
db_pool = MySQLConnectionPool(**Config.DB_CONFIG)

# Initialize Flask app
app = Flask(__name__)
app.config.update(
    SECRET_KEY=Config.FLASK_SECRET_KEY,
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=Config.FLASK_SESSION_COOKIE_SECURE,
)


# Enable CORS
CORS(
    app,
    supports_credentials=True,
    expose_headers=["RethinkAI-API-Key"],
    resources={r"/*": {"origins": "*"}},
)


#
# Font colors for error/print
#
class Font_Colors:
    PASS = "\033[92m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


#
# Class for structured data response from llm
#
class Structured_Data(BaseModel):
    living_conditions: str
    parking: str
    streets: str
    trash: str


#
# SQL Query Constants
#
class SQLConstants:
    # TNT neighborhood coordinates. Using less specific rectangular shape for now.
    # Format: "lng_bottom_left lat_bottom_left, lng_top_left lat_top_left, lng_top_right lat_top_right, lng_bottom_right lat_bottom_right, lng_bottom_left lat_bottom_left"
    DEFAULT_POLYGON_COORDINATES = "-71.081297 42.284182, -71.081784 42.293107, -71.071730 42.293255, -71.071601 42.284301, -71.081297 42.284182"

    # 311 category mappings
    CATEGORY_TYPES = {
        "living_conditions": "'Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential'",
        "trash": "'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping'",
        "streets": "'Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair'",
        "parking": "'Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints'",
    }

    # Set the 'all' category to include all individual categories
    CATEGORY_TYPES["all"] = ", ".join(
        [cat for cat in ", ".join(CATEGORY_TYPES.values()).split(", ")]
    )

    BOS311_NORMALIZED_TYPE_CASE = f"""
    CASE
        WHEN type IN ({CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
        WHEN type IN ({CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
        WHEN type IN ({CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
        WHEN type IN ({CATEGORY_TYPES['parking']}) THEN 'Parking'
    END AS normalized_type,
    """
    # Common aggregation columns for monthly/quarterly breakdowns
    BOS911_TIME_BREAKDOWN = """
    COUNT(*) AS total_by_year,
    SUM(CASE WHEN quarter = 1 THEN 1 ELSE 0 END) AS q1_total,
    SUM(CASE WHEN quarter = 2 THEN 1 ELSE 0 END) AS q2_total,
    SUM(CASE WHEN quarter = 3 THEN 1 ELSE 0 END) AS q3_total,
    SUM(CASE WHEN quarter = 4 THEN 1 ELSE 0 END) AS q4_total,
    SUM(CASE WHEN month = 1 THEN 1 ELSE 0 END) AS jan_total,
    SUM(CASE WHEN month = 2 THEN 1 ELSE 0 END) AS feb_total,
    SUM(CASE WHEN month = 3 THEN 1 ELSE 0 END) AS mar_total,
    SUM(CASE WHEN month = 4 THEN 1 ELSE 0 END) AS apr_total,
    SUM(CASE WHEN month = 5 THEN 1 ELSE 0 END) AS may_total,
    SUM(CASE WHEN month = 6 THEN 1 ELSE 0 END) AS jun_total,
    SUM(CASE WHEN month = 7 THEN 1 ELSE 0 END) AS jul_total,
    SUM(CASE WHEN month = 8 THEN 1 ELSE 0 END) AS aug_total,
    SUM(CASE WHEN month = 9 THEN 1 ELSE 0 END) AS sep_total,
    SUM(CASE WHEN month = 10 THEN 1 ELSE 0 END) AS oct_total,
    SUM(CASE WHEN month = 11 THEN 1 ELSE 0 END) AS nov_total,
    SUM(CASE WHEN month = 12 THEN 1 ELSE 0 END) AS dec_total
    """

    BOS311_TIME_BREAKDOWN = """
    COUNT(*) AS total_by_year,
    SUM(CASE WHEN QUARTER(open_dt) = 1 THEN 1 ELSE 0 END) AS q1_total,
    SUM(CASE WHEN QUARTER(open_dt) = 2 THEN 1 ELSE 0 END) AS q2_total,
    SUM(CASE WHEN QUARTER(open_dt) = 3 THEN 1 ELSE 0 END) AS q3_total,
    SUM(CASE WHEN QUARTER(open_dt) = 4 THEN 1 ELSE 0 END) AS q4_total,
    SUM(CASE WHEN MONTH(open_dt) = 1 THEN 1 ELSE 0 END) AS jan_total,
    SUM(CASE WHEN MONTH(open_dt) = 2 THEN 1 ELSE 0 END) AS feb_total,
    SUM(CASE WHEN MONTH(open_dt) = 3 THEN 1 ELSE 0 END) AS mar_total,
    SUM(CASE WHEN MONTH(open_dt) = 4 THEN 1 ELSE 0 END) AS apr_total,
    SUM(CASE WHEN MONTH(open_dt) = 5 THEN 1 ELSE 0 END) AS may_total,
    SUM(CASE WHEN MONTH(open_dt) = 6 THEN 1 ELSE 0 END) AS jun_total,
    SUM(CASE WHEN MONTH(open_dt) = 7 THEN 1 ELSE 0 END) AS jul_total,
    SUM(CASE WHEN MONTH(open_dt) = 8 THEN 1 ELSE 0 END) AS aug_total,
    SUM(CASE WHEN MONTH(open_dt) = 9 THEN 1 ELSE 0 END) AS sep_total,
    SUM(CASE WHEN MONTH(open_dt) = 10 THEN 1 ELSE 0 END) AS oct_total,
    SUM(CASE WHEN MONTH(open_dt) = 11 THEN 1 ELSE 0 END) AS nov_total,
    SUM(CASE WHEN MONTH(open_dt) = 12 THEN 1 ELSE 0 END) AS dec_total
    """

    # 311 specific constants
    BOS311_BASE_WHERE = f"""
    ST_Contains(
        ST_GeomFromText('POLYGON(({DEFAULT_POLYGON_COORDINATES}))'),
        coordinates
    )
    """

    # BOS311_BASE_WHERE = (
    #     "police_district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester'"
    # )

    # 911 specific constants
    BOS911_BASE_WHERE = "district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester' AND year >= 2018 AND year < 2025"

    # BOS911_BASE_WHERE = f"""
    # ST_Contains(
    #     ST_GeomFromText('POLYGON(({DEFAULT_POLYGON_COORDINATES}))'),
    #     coordinates
    # )
    # """


#
# Query Builders
#
def build_311_query(
    data_request: str,
    request_options: str = "",
    request_date: str = "",
    request_zipcode: str = "",
    event_ids: str = "",
) -> str:
    if data_request == "311_by_geo" and request_options:
        query = f"""
        SELECT
            id,
            type,
            open_dt AS date,
            latitude,
            longitude,
            CASE
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
            END AS normalized_type
        FROM
            bos311_data
        WHERE
            type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        """
        if request_date:
            query += f"""AND DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'"""

        return query
    elif data_request == "311_summary_context":
        query = f"""
        WITH category_aggregates AS (
            SELECT
                year,
                '911 Shot Fired Confirmed - Annual Total' AS incident_type,
                {SQLConstants.BOS911_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM shots_fired_data
            WHERE {SQLConstants.BOS911_BASE_WHERE}
            AND ballistics_evidence = 1
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                year,
                '911 Shot Fired Unconfirmed - Annual Total' AS incident_type,
                {SQLConstants.BOS911_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM shots_fired_data
            WHERE {SQLConstants.BOS911_BASE_WHERE}
            AND ballistics_evidence = 0
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                year,
                '911 Homicides - Annual Total' AS incident_type,
                {SQLConstants.BOS911_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM homicide_data
            WHERE {SQLConstants.BOS911_BASE_WHERE}
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Trash & Dumping Issues - Annual Total' AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['trash']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Living Condition Issues - Annual Total' AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Streets Issues - Annual Total' AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['streets']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, incident_type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Parking Issues - Annual Total' AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['parking']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, incident_type
        ),
        type_details AS (
            SELECT
                YEAR(open_dt) AS year,
                '311 Trash & Dumping Issues' AS category,
                type AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Type' AS level_type
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['trash']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Living Condition Issues' AS category,
                type AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Type' AS level_type
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Streets Issues' AS category,
                type AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Type' AS level_type
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['streets']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, type
            UNION ALL
            SELECT
                YEAR(open_dt) AS year,
                '311 Parking Issues' AS category,
                type AS incident_type,
                {SQLConstants.BOS311_TIME_BREAKDOWN},
                'Type' AS level_type
            FROM bos311_data
            WHERE type IN ({SQLConstants.CATEGORY_TYPES['parking']})
            AND {SQLConstants.BOS311_BASE_WHERE}
            GROUP BY year, type
        )
        SELECT
            year,
            incident_type,
            total_by_year,
            q1_total, q2_total, q3_total, q4_total,
            jan_total, feb_total, mar_total, apr_total, may_total, jun_total,
            jul_total, aug_total, sep_total, oct_total, nov_total, dec_total,
            level_type,
            category
        FROM category_aggregates
        UNION ALL
        SELECT
            year,
            incident_type,
            total_by_year,
            q1_total, q2_total, q3_total, q4_total,
            jan_total, feb_total, mar_total, apr_total, may_total, jun_total,
            jul_total, aug_total, sep_total, oct_total, nov_total, dec_total,
            level_type,
            category
        FROM type_details
        ORDER BY
            year,
            CASE
                WHEN category = '311 Trash & Dumping Issues' OR incident_type = '311 Trash & Dumping Issues - Annual Total' THEN 1
                WHEN category = '311 Living Condition Issues' OR incident_type = '311 Living Condition Issues - Annual Total' THEN 2
                WHEN category = '311 Streets Issues' OR incident_type = '311 Streets Issues - Annual Total' THEN 3
                WHEN category = '311 Parking Issues' OR incident_type = '311 Parking Issues - Annual Total' THEN 4
                WHEN incident_type = '911 Shot Fired Confirmed - Annual Total' THEN 5
                WHEN incident_type = '911 Shot Fired Unconfirmed - Annual Total' THEN 6
                WHEN incident_type = '911 Homicides - Annual Total' THEN 7
                ELSE 8
            END,
            CASE
                WHEN level_type = 'Category' THEN 2
                ELSE 1
            END,
            incident_type;
            """
        return query
    elif data_request == "311_summary" and event_ids:
        query = f"""
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        type AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE id IN ({event_ids})
        GROUP BY category, subcategory
        UNION ALL
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        'TOTAL' AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE id IN ({event_ids})
        GROUP BY
        category
        ORDER BY
        category,
        CASE
            WHEN subcategory = 'TOTAL' THEN 2
            ELSE 1
        END,
        total DESC;
        """
        return query
    elif data_request == "311_summary" and request_date and request_options:
        query = f"""
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        type AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE
            DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'
            AND type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY category, subcategory
        UNION ALL
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        'TOTAL' AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE
            DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'
            AND type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY
        category
        ORDER BY
        category,
        CASE
            WHEN subcategory = 'TOTAL' THEN 2
            ELSE 1
        END,
        total DESC;
        """
        return query
    elif (
        data_request == "311_summary"
        and not request_date
        and not event_ids
        and request_options
    ):
        query = f"""
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        type AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE
            type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY category, subcategory
        UNION ALL
        SELECT
        CASE
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
            WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
        END AS category,
        'TOTAL' AS subcategory,
        COUNT(*) AS total
        FROM bos311_data
        WHERE
            type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY
        category
        ORDER BY
        category,
        CASE
            WHEN subcategory = 'TOTAL' THEN 2
            ELSE 1
        END,
        total DESC;
        """
        return query
    else:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating query:{Font_Colors.ENDC}: check query args"
        )
        return ""


def build_911_query(data_request: str) -> str:
    if data_request == "911_shots_fired":
        return f"""
        SELECT
            id,
            incident_date_time AS date,
            ballistics_evidence,
            latitude,
            longitude
        FROM shots_fired_data
        WHERE {SQLConstants.BOS911_BASE_WHERE}
        AND latitude IS NOT NULL
        AND longitude IS NOT NULL
        GROUP BY id, date, ballistics_evidence, latitude, longitude;
        """
    elif data_request == "911_homicides_and_shots_fired":
        return """
        SELECT
            s.id as id,
            h.homicide_date as date,
            s.latitude as latitude,
            s.longitude as longitude
        FROM
            shots_fired_data s
        INNER JOIN
            homicide_data h
        ON
            DATE(s.incident_date_time) = DATE(h.homicide_date)
            AND s.district = h.district
        WHERE
            s.ballistics_evidence = 1
            AND h.district IN ('B3', 'C11', 'B2')
            AND h.neighborhood = 'Dorchester'
            AND s.year >= 2018
            AND s.year < 2025
        """
    return ""


#
# Helper functions
#


# Checks if a string is in 'YYYY-MM' format.
def check_date_format(date_string: str) -> bool:
    pattern = r"^\d{4}-\d{2}$"
    if not re.match(pattern, date_string):
        return False

    year, month = map(int, date_string.split("-"))
    return 1 <= month <= 12


def check_filetype(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def get_files(
    file_type: Optional[str] = None, specific_files: Optional[List[str]] = None
) -> List[str]:
    """Get a list of files from the datastore directory."""
    try:
        if not Config.DATASTORE_PATH.exists():
            return []

        if specific_files:
            return [
                f.name
                for f in Config.DATASTORE_PATH.iterdir()
                if f.is_file()
                and f.name in specific_files
                and not f.name.startswith(".")
            ]

        if file_type:
            return [
                f.name
                for f in Config.DATASTORE_PATH.iterdir()
                if f.is_file()
                and f.suffix.lower() == f".{file_type}"
                and not f.name.startswith(".")
            ]

        return [
            f.name
            for f in Config.DATASTORE_PATH.iterdir()
            if f.is_file() and not f.name.startswith(".")
        ]

    except Exception as e:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error getting files:{Font_Colors.ENDC} {e}"
        )
        return []


def get_file_content(filename: str) -> Optional[str]:
    """Read content from a file in the datastore."""
    try:
        file_path = Config.DATASTORE_PATH / filename
        if not file_path.exists():
            return None

        return file_path.read_text(encoding="utf-8")

    except Exception as e:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error reading file {filename}:{Font_Colors.ENDC} {e}"
        )
        return None


# DB Connection
def get_db_connection():
    # return mysql.connector.connect(**Config.DB_CONFIG)
    return db_pool.get_connection()


def json_query_results(query: str) -> Optional[Response]:
    """Execute a database query and return results as JSON."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        result = cursor.fetchall()
        return jsonify(result) if result else None
    except mysql.connector.Error as err:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error in database connection (json_query_results):{Font_Colors.ENDC} {str(err)}"
        )
        return None
    finally:
        if "cursor" in locals() and cursor:
            cursor.close()
        if "conn" in locals() and conn:
            conn.close()


def stream_query_results(query: str) -> Generator[str, None, None]:
    """Execute a database query and stream results as JSON."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)

        yield "[\n"
        first_row = True
        for row in cursor:
            if not first_row:
                yield ",\n"
            else:
                first_row = False

            # Convert mysql objects to something json-friendly
            processed_row = {}
            for key, value in row.items():
                if hasattr(value, "isoformat"):
                    processed_row[key] = value.isoformat()
                elif isinstance(value, decimal.Decimal):
                    processed_row[key] = float(value)
                else:
                    processed_row[key] = value
            yield json.dumps(processed_row)

        # Close the JSON structure
        yield "\n]"
    except mysql.connector.Error as err:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error in database connection (stream_query_results):{Font_Colors.ENDC} {str(err)}"
        )
        yield "[]\n"  # Return empty array on error
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def csv_query_results(query: str) -> Optional[io.StringIO]:
    """Execute a database query and return results as CSV in a StringIO object."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)

        fieldnames = [desc[0] for desc in cursor.description]
        result = io.StringIO()
        writer = csv.DictWriter(result, fieldnames=fieldnames)
        writer.writeheader()
        for row in cursor:
            writer.writerow(row)
        return result
    except mysql.connector.Error as err:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error in database connection (csv_query_results):{Font_Colors.ENDC} {str(err)}"
        )
        return None
    finally:
        if "cursor" in locals() and cursor:
            cursor.close()
        if "conn" in locals() and conn:
            conn.close()


def get_query_results(query: str, output_type: str = ""):
    if output_type == "stream":
        return stream_query_results(query)
    elif output_type == "csv":
        return csv_query_results(query)
    elif output_type == "json" or output_type == "":
        return json_query_results(query)
    else:
        raise ValueError(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error getting query results:{Font_Colors.ENDC} Invalid output_type: {output_type}"
        )


def get_gemini_response(
    prompt: str, cache_name: str, structured_response: bool = False
) -> str:
    try:
        model = Config.GEMINI_MODEL
        if structured_response is True:
            config = types.GenerateContentConfig(
                cached_content=cache_name,
                response_schema=list[Structured_Data],
                response_mime_type="application/json",
            )
        else:
            config = types.GenerateContentConfig(cached_content=cache_name)

        # Direct synchronous call instead of asyncio.to_thread
        response = genai_client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return response.text

    except Exception as e:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating response:{Font_Colors.ENDC} {e}"
        )
        return f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating response:{Font_Colors.ENDC} {e}"


def create_gemini_context(
    context_request: str,
    preamble: str = "",
    generate_cache: bool = True,
    app_version: str = "",
) -> Union[str, int, bool]:
    # test if cache exists
    if generate_cache:
        for cache in genai_client.caches.list():
            if (
                cache.display_name
                == "APP_VERSION_" + app_version + "_REQUEST_" + context_request
                and cache.model == Config.GEMINI_MODEL
            ):
                return cache.name

    try:
        files_list = []
        content = {"parts": []}

        # adding community assets to context (ignoring potential other csv in datastore)
        if context_request == "structured":
            files_list = get_files("csv", ["geocoding-community-assets.csv"])
            preamble_file = context_request + ".txt"

        elif context_request == "unstructured":
            files_list = get_files("txt")
            preamble_file = context_request + ".txt"

        elif context_request == "all":
            files_list = get_files()
            preamble_file = context_request + ".txt"
        elif (
            context_request == "experiment_5"
            or context_request == "experiment_6"
            or context_request == "experiment_7"
            or context_request == "experiment_pit"
            or context_request == "get_summary"
        ):
            files_list = get_files("txt")
            query = build_311_query(data_request="311_summary_context")
            response = get_query_results(query=query, output_type="csv")

            content["parts"].append({"text": response.getvalue()})

            preamble_file = context_request + ".txt"

        # Read contents of found files
        for file in files_list:
            file_content = get_file_content(file)
            if file_content is not None:
                content["parts"].append({"text": file_content})

        path = Config.PROMPTS_PATH / preamble_file
        if not path.is_file():
            raise FileNotFoundError(
                f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error: File not found:{Font_Colors.ENDC} {path}"
            )
        system_prompt = path.read_text(encoding="utf-8")

        display_name = "APP_VERSION_" + app_version + "_REQUEST_" + context_request

        # Generate cache or return token count
        if generate_cache:
            # Set cache expiration time
            cache_ttl = (
                (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=Config.GEMINI_CACHE_TTL)
                )
                .isoformat()
                .replace("+00:00", "Z")
            )

            # Create the cache
            cache = genai_client.caches.create(
                model=Config.GEMINI_MODEL,
                config=types.CreateCachedContentConfig(
                    display_name=display_name,
                    system_instruction=system_prompt,
                    expire_time=cache_ttl,
                    contents=content["parts"],
                ),
            )

            return cache.name
        else:
            # Return token count for testing
            content["parts"].append({"text": system_prompt})
            total_tokens = genai_client.models.count_tokens(
                model=Config.GEMINI_MODEL, contents=content["parts"]
            )
            return total_tokens.total_tokens

    except Exception as e:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating context:{Font_Colors.ENDC} {e}"
        )
        return f"✖ Error generating context: {e}"


# Log events
def log_event(
    session_id: str,
    app_version: str,
    data_selected: str = "",
    data_attributes: str = "",
    prompt_preamble: str = "",
    client_query: str = "",
    app_response: str = "",
    client_response_rating: str = "",
    log_id: str = "",
) -> Union[int, bool]:
    """Log an event to the database."""
    if not session_id or not app_version:
        print("Missing session_id or app_version")
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert new entry if no log_id provided
        if not log_id:
            query = """
                INSERT INTO interaction_log (
                    session_id, app_version, data_selected, data_attributes,
                    prompt_preamble, client_query, app_response, client_response_rating
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """

            cursor.execute(
                query,
                (
                    session_id,
                    app_version,
                    data_selected,
                    data_attributes,
                    prompt_preamble,
                    client_query,
                    app_response,
                    client_response_rating,
                ),
            )

            app_response_id = cursor.lastrowid
        else:
            # Create a dictionary of non-empty fields to update
            update_fields = {
                "app_version": app_version,
                "data_selected": data_selected,
                "data_attributes": data_attributes,
                "prompt_preamble": prompt_preamble,
                "client_query": client_query,
                "app_response": app_response,
                "client_response_rating": client_response_rating,
            }

            # Filter out empty fields
            update_fields = {k: v for k, v in update_fields.items() if v}

            if update_fields:
                # Build the query dynamically
                update_parts = [f"{field} = %s" for field in update_fields]
                query = f"UPDATE interaction_log SET {', '.join(update_parts)} WHERE id = %s"

                # Add values in the correct order
                params = list(update_fields.values())
                params.append(log_id)

                cursor.execute(query, params)

            app_response_id = log_id

        conn.commit()
        return app_response_id

    except mysql.connector.Error as err:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error in database connection (log_event):{Font_Colors.ENDC} {str(err)}"
        )
        return False

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


#
# Middleware to check session and create if needed
#
@app.before_request
def check_session():
    if request.method == "OPTIONS":
        # Preflight CORS request – skip auth
        return None

    rethinkai_api_client_key = request.headers.get("RethinkAI-API-Key")
    app_version = request.args.get("app_version", "")

    if (
        not rethinkai_api_client_key
        or rethinkai_api_client_key not in Config.RETHINKAI_API_KEYS
    ):
        return jsonify({"Error": "Invalid or missing API key"}), 401

    if "session_id" not in session:
        session.permanent = True  # Make the session persistent
        session["session_id"] = str(uuid.uuid4())
        log_event(
            session_id=session["session_id"],
            app_version=app_version,
            data_attributes=Config.API_VERSION,
            app_response="New session created",
        )

    # Log the request
    g.log_entry = log_event(
        session_id=session["session_id"],
        app_version=app_version,
        data_attributes=Config.API_VERSION,
        client_query=f"Request: [{request.method}] {request.url}",
    )


#
# Endpoint Definitions
#
@app.route("/data/query", methods=["GET", "POST"])
def route_data_query():
    session_id = session.get("session_id")
    # Get query parameters
    app_version = request.args.get("app_version", "0")
    stream_result = request.args.get("stream", "False")
    request_zipcode = request.args.get("zipcode", "")
    event_ids = request.args.get("event_ids", "")
    request_date = request.args.get("date", "")
    data_request = request.args.get("request", "")
    output_type = request.args.get("output_type", "")

    if not data_request:
        return jsonify({"✖ Error": "Missing data_request parameter"}), 400

    if request.method == "POST":
        # Handles case for requesting many event_ids
        data = request.get_json()
        event_ids = data.get("event_ids", "")

    try:  # Get and validate request parameters
        request_options = request.args.get("category", "")
        if data_request.startswith("311_by") and not request_options:
            return (
                jsonify(
                    {"✖ Error": "Missing required options parameter for 311 request"}
                ),
                400,
            )

        if data_request.startswith("311_on_date") and not request_date:
            return (
                jsonify(
                    {"✖ Error": "Missing required options parameter for 311 request"}
                ),
                400,
            )

        # Validate date format for date-specific queries
        if data_request.startswith("311_on_date") and not check_date_format(
            request_date
        ):
            return jsonify({"✖ Error": 'Incorrect date format. Expects "YYYY-MM"'}), 400

        # Build query using the appropriate query builder
        if data_request.startswith("311"):
            query = build_311_query(
                data_request=data_request,
                request_options=request_options,
                request_date=request_date,
                request_zipcode=request_zipcode,
                event_ids=event_ids,
            )

        elif data_request.startswith("911"):
            query = build_911_query(data_request=data_request)
        elif data_request == "zip_geo":
            query = f"""
            SELECT JSON_OBJECT(
                'type', 'FeatureCollection',
                'features', JSON_ARRAYAGG(
                    JSON_OBJECT(
                        'type', 'Feature',
                        'geometry', ST_AsGeoJSON(boundary),
                        'properties', JSON_OBJECT('zipcode', zipcode)
                    )
                )
            )
            FROM zipcode_geo
            WHERE zipcode IN ({request_zipcode})
            """
        else:
            return jsonify({"✖ Error": "Invalid data_request parameter"}), 400

        if not query:
            return jsonify({"✖ Error": "Failed to build query"}), 500

        # Return w/ streaming
        if stream_result == "True":
            # return Response(stream_with_context(stream_query_results(query=query)), mimetype="application/json")
            return Response(
                stream_with_context(
                    get_query_results(query=query, output_type="stream")
                ),
                mimetype="application/json",
            )
        # Return non-streaming
        else:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            result = get_query_results(query=query, output_type=output_type)
            if output_type == "csv" and result:
                output = result.getvalue()
                response = Response(output, mimetype="text/csv")
                response.headers["Content-Disposition"] = (
                    "attachment; filename=export.csv"
                )
                return response
            return result

    except Exception as e:
        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response=f"ERROR: {str(e)}",
        )
        return jsonify({"✖ Error": str(e)}), 500


@app.route("/chat", methods=["POST"])
def route_chat():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    context_request = request.args.get(
        "context_request", request.args.get("request", "")
    )
    structured_response = request.args.get("structured_response", False)

    data = request.get_json()

    # Extract chat data parameters
    data_attributes = data.get("data_attributes", "")
    client_query = data.get("client_query", "")
    prompt_preamble = data.get("prompt_preamble", "")

    # data_selected, optional, list of files used when context_request==s
    cache_name = create_gemini_context(
        context_request=context_request,
        preamble=prompt_preamble,
        generate_cache=True,
        app_version=app_version,
    )

    full_prompt = f"User question: {client_query}"

    # Process chat
    try:
        app_response = get_gemini_response(
            prompt=full_prompt,
            cache_name=cache_name,
            structured_response=structured_response,
        )
        if "Error" in app_response:
            print(
                f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ ERROR from Gemini API:{Font_Colors.ENDC} {app_response}"
            )
            return jsonify({"Error": app_response}), 500

        # Log the interaction
        log_id = log_event(
            session_id=session_id,
            app_version=app_version,
            data_selected=context_request,
            data_attributes=data_attributes,
            prompt_preamble=prompt_preamble,
            client_query=full_prompt,
            app_response=app_response,
        )
        response = {
            "session_id": session_id,
            "response": app_response,
            "log_id": log_id,
        }

        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response="SUCCESS",
        )
        return jsonify(response)

    except Exception as e:
        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response=f"ERROR: {str(e)}",
        )
        print(f"✖ Exception in /chat: {e}")
        print(f"✖ context_request: {context_request}")
        print(f"✖ preamble: {prompt_preamble}")
        print(f"✖ app_version: {app_version}")
        return jsonify({"Error": f"Internal server error: {e}"}), 500


@app.route("/chat/context", methods=["GET", "POST"])
def route_chat_context():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    context_request = request.args.get(
        "context_request", request.args.get("request", "")
    )

    if request.method == "GET":
        # return list of context caches if <request> is ""
        if not context_request:
            response = {cache.name: str(cache) for cache in genai_client.caches.list()}
            return jsonify(response)

        else:
            # test token count for context cache of <request>
            token_count = create_gemini_context(
                context_request=context_request,
                preamble="",
                generate_cache=False,
                app_version=app_version,
            )

            if isinstance(token_count, int):
                return jsonify({"token_count": token_count})
            elif hasattr(token_count, "total_tokens") and isinstance(
                token_count.total_tokens, int
            ):
                return jsonify({"token_count": token_count.total_tokens})
            else:
                # Handle the error appropriately, e.g., log the error and return an error response
                print(
                    f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error getting token count:{Font_Colors.ENDC} {token_count}"
                )  # Log the error
                return (
                    jsonify({"error": "Failed to get token count"}),
                    500,
                )  # Return an error response
    if request.method == "POST":
        # TODO: implement 'specific' context_request with list of files from datastore
        # FOR NOW: assumes 'structured', 'unstructured', 'all', 'experiment_5', 'experiment_6', 'experiment_7' context_request
        # Context cache creation appends app_version so caches are versioned.
        if not context_request:
            return jsonify({"Error": "Missing context_request parameter"}), 400

        context_option = request.args.get("option", "")
        if context_option == "clear":
            # clear the cache, either by name or all existing caches
            for cache in genai_client.caches.list():
                if context_request == cache.display_name or context_request == "all":
                    genai_client.caches.delete(name=cache.name)

            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            return jsonify({"Success": "Context cache cleared."})
        else:
            data = request.get_json()
            # Extract chat data parameters
            prompt_preamble = data.get("prompt_preamble", "")

            response = create_gemini_context(
                context_request=context_request,
                preamble=prompt_preamble,
                generate_cache=True,
                app_version=app_version,
            )

            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            return jsonify(response)


@app.route("/chat/summary", methods=["POST"])
def chat_summary():
    data = request.get_json()
    messages = data.get("messages", [])
    app_version = request.args.get("app_version", "0")

    if not messages:
        return jsonify({"error": "No messages provided."}), 400

    chat_transcript = "\n".join(
        f"{'User' if msg['sender'] == 'user' else 'Chat'}: {msg['text']}"
        for msg in messages
    )

    cache_name = create_gemini_context(
        context_request="get_summary",
        preamble="",
        generate_cache=True,
        app_version=app_version,
    )

    try:
        summary = get_gemini_response(prompt=chat_transcript, cache_name=cache_name)
        return jsonify({"summary": summary})

    except Exception as e:
        print(f"✖ Error summarizing chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/log", methods=["POST", "PUT"])
def route_log():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    # log_switch = request.args.get("log_action", "")
    data = request.get_json()

    if request.method == "POST":
        log_id = log_event(
            session_id=session_id,
            app_version=app_version,
            data_selected=data.get("data_selected", ""),
            data_attributes=data.get("data_attributes", ""),
            prompt_preamble=data.get("prompt_preambe", ""),
            client_query=data.get("client_query", ""),
            app_response=data.get("app_response", ""),
            client_response_rating=data.get("client_response_rating", ""),
            log_id=data.get("log_id", ""),
        )
        if log_id != 0:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            return (
                jsonify(
                    {"message": "Log entry created successfully", "log_id": log_id}
                ),
                201,
            )
        else:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="ERROR: Log entry not created",
            )
            return jsonify({"Error": "Failed to create log entry"}), 500
    if request.method == "PUT":
        if not data.get("log_id", ""):
            return jsonify({"Error": "Missing log_id to update"}), 500

        log_id = log_event(
            session_id=session_id,
            app_version=app_version,
            data_selected=data.get("data_selected", ""),
            data_attributes=data.get("data_attributes", ""),
            prompt_preamble=data.get("prompt_preambe", ""),
            client_query=data.get("client_query", ""),
            app_response=data.get("app_response", ""),
            client_response_rating=data.get("client_response_rating", ""),
            log_id=data.get("log_id", ""),
        )
        if log_id != 0:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            return (
                jsonify(
                    {"message": "Log entry updated successfully", "log_id": log_id}
                ),
                201,
            )
        else:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="ERROR: Log entry not updated",
            )
            return jsonify({"Error": "Failed to update log entry"}), 500


@app.route("/llm_summaries", methods=["GET"])
def route_llm_summary():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")
    month = request.args.get("month", request.args.get("date", ""))

    if not month:
        return jsonify({"Error"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT summary FROM llm_summaries WHERE month_label = %s", (month,)
        )
        row = cursor.fetchone()

        if not row:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="ERROR",
            )
            return jsonify({"summary": "[No summary available for this month]"}), 404

        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response="SUCCESS",
        )
        return jsonify({"month": month, "summary": row["summary"]})

    except Exception as e:
        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response=f"ERROR: {str(e)}",
        )
        return jsonify({"Error": str(e)}), 500

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


@app.route("/llm_summaries/all", methods=["GET"])
def route_all_llm_summaries():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT month_label, summary FROM llm_summaries ORDER BY month_label ASC"
        )
        rows = cursor.fetchall()

        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response="SUCCESS",
        )

        return jsonify(rows)

    except Exception as e:
        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response=f"ERROR: {str(e)}",
        )
        return jsonify({"Error": str(e)}), 500

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
