"""
api.py

This module contains the main API logic for the application, handling requests, processing data, and interacting with the database and external services.
It includes endpoints for querying 311 and 911 data, generating responses from the Gemini AI model, and serving static files.
It also includes utility functions for file handling, database connections, and response formatting.
It is designed to be used with Flask and supports CORS for cross-origin requests.
"""

import faulthandler

faulthandler.enable()
print("=== api.py start ===")

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

from geospatial_context import process_geospatial_message

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
    BASE_URL = os.getenv("VITE_BASE_URL")
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
    allow_headers=["Content-Type", "RethinkAI-API-Key"],
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

    ##### 311 specific constants #####

    # Base WHERE clause for 311 queries, not using neighborhood coordinates
    # This is a simplified version that provides backward compatibility
    BOS311_BASE_WHERE = (
        "police_district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester'"
    )

    # Spatial WHERE clause for 311 queries, using neighborhood coordinates
    # Uses a polygon that covers the TNT area
    BOS311_SPATIAL_WHERE = f"""
    ST_Contains(
        ST_GeomFromText('POLYGON(({DEFAULT_POLYGON_COORDINATES}))'),
        coordinates
    ) = 1
    """

    ##### 911 specific constants #####

    # Base WHERE clause for 911 queries, not using neighborhood coordinates
    # This is a simplified version that provides backward compatibility
    BOS911_BASE_WHERE = "district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester' AND year >= 2018 AND year < 2025"

    # Spatial WHERE clause for 911 queries, using neighborhood coordinates
    # Uses a polygon that covers the TNT area
    BOS911_SPATIAL_WHERE = f"""
    year >= 2018 AND year < 2025
    AND ST_Contains(
        ST_GeomFromText('POLYGON(({DEFAULT_POLYGON_COORDINATES}))'),
        coordinates
    ) = 1
    """


#
# Query Builders
#
def build_311_query(
    data_request: str,
    request_options: str = "",
    request_date: str = "",
    request_zipcode: str = "",
    event_ids: str = "",
    is_spatial=False,
) -> str:
    
    """
    Build SQL query for 311 data based on the request type and parameters.

    Args:
        data_request (str): The type of data request (e.g., "311_by_geo", "311_summary_context", "311_summary").
        request_options (str, optional): Specific options for the request, such as categories or types.
        request_date (str, optional): Date in 'YYYY-MM' format for filtering results.
        request_zipcode (str, optional): Zipcode for filtering results.
        event_ids (str, optional): Comma-separated list of event IDs for specific queries.
        is_spatial (bool, optional): Whether to use spatial queries based on coordinates.

    Returns:
        str: The constructed SQL query string.

    Raises:
        None, but prints an error message and returns an empty string if the data_request is not recognized
    """

    # Set the WHERE clause based on whether the query is looking for TNT-specific data or not
    if is_spatial:
        Bos311_where_clause = SQLConstants.BOS311_SPATIAL_WHERE
        Bos911_where_clause = SQLConstants.BOS911_SPATIAL_WHERE
    else:
        Bos311_where_clause = SQLConstants.BOS311_BASE_WHERE
        Bos911_where_clause = SQLConstants.BOS911_BASE_WHERE

    if data_request == "311_by_geo" and request_options: 
        # This query is used to get 311 data by geographic area
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
            AND {Bos311_where_clause}
        """

        if request_date:
            query += f"""AND DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'"""

        return query
    elif data_request == "311_summary_context":
        # This query is used to generate a summary of 311 data for context in the Gemini model
        query = f"""
        WITH category_aggregates AS (
            SELECT
                year,
                '911 Shot Fired Confirmed - Annual Total' AS incident_type,
                {SQLConstants.BOS911_TIME_BREAKDOWN},
                'Category' AS level_type,
                NULL AS category
            FROM shots_fired_data
            WHERE {Bos911_where_clause}
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
            WHERE {Bos911_where_clause}
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
            WHERE {SQLConstants.BOS911_BASE_WHERE} # Always uses base where clause because it's pulling from homicide_data, which doesn't have coordinates
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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

        # Quote each event_id if not already quoted
        id_list = [f"'{x.strip()}'" for x in event_ids.split(",") if x.strip()]
        id_str = ",".join(id_list)
        
        # This query is used to summarize 311 data for specific event IDs
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
        WHERE id IN ({id_str})
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
        WHERE id IN ({id_str})
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
        # This query is used to summarize 311 data for a specific date and request options
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
        # This query is used to summarize 311 data for specific request options without date or event IDs
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
            AND {Bos311_where_clause}
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
            AND {Bos311_where_clause}
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
        # If the data_request is not recognized, print an error message and return an empty string
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating query:{Font_Colors.ENDC}: check query args"
        )
        return ""


def build_911_query(data_request: str, is_spatial=False) -> str:
    """
    Build SQL query for 911 data based on the request type.

    Args:
        data_request (str): The type of data request (e.g., "911_shots_fired", "911_homicides_and_shots_fired").
        is_spatial (bool, optional): Whether to use spatial queries based on coordinates.

    Returns:
        str: The constructed SQL query string.
    
    Raises:
        None, but returns an empty string if the data_request is not recognized.
    """

    Bos911_where_clause = (
        SQLConstants.BOS911_SPATIAL_WHERE
        if is_spatial
        else SQLConstants.BOS911_BASE_WHERE
    )

    if data_request == "911_shots_fired":
        query = f"""
        SELECT
            id,
            incident_date_time AS date,
            ballistics_evidence,
            latitude,
            longitude
        FROM shots_fired_data
        WHERE {Bos911_where_clause}
            AND latitude IS NOT NULL
            AND longitude IS NOT NULL
        GROUP BY id, date, ballistics_evidence, latitude, longitude;
        """

        return query
    elif data_request == "911_homicides_and_shots_fired":
        return f"""
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


def check_date_format(date_string: str) -> bool:
    """
    Check if the given date string is in 'YYYY-MM' format and if the month is valid.

    Args:
        date_string (str): The date string to check.
    
    Returns:
        bool: True if the date string is in 'YYYY-MM' format and the month is valid, False otherwise.

    Raises:
        None
    """
    
    pattern = r"^\d{4}-\d{2}$"
    if not re.match(pattern, date_string):
        return False

    year, month = map(int, date_string.split("-"))
    return 1 <= month <= 12


def check_filetype(filename: str) -> bool:
    """
    Check if the given filename has an allowed file extension.

    Args:
        filename (str): The name of the file to check.

    Returns:
        bool: True if the file has an allowed extension, False otherwise.
    
    Raises:
        None 
    """
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS
    )


def get_files(
    file_type: Optional[str] = None, specific_files: Optional[List[str]] = None
) -> List[str]:
    """
    Get a list of files from the datastore directory.
    
    Args:
        file_type (str, optional): The type of file to filter by (e.g., "csv", "txt").
        specific_files (List[str], optional): A list of specific filenames to retrieve.
    
    Returns:
        List[str]: A list of filenames in the datastore directory that match the criteria.
    
    Raises:
        Exception: If there is an error accessing the datastore directory or reading files.
    """
    # changing get_files as it was only getting the .txt files, to ensured it would also get community assets csv
    try:
        if not Config.DATASTORE_PATH.exists():
            return []

        files = []

        if specific_files:
            files = [
                f.name
                for f in Config.DATASTORE_PATH.iterdir()
                if f.is_file()
                and f.name in specific_files
                and not f.name.startswith(".")
            ]

        elif file_type:
            files = [
                f.name
                for f in Config.DATASTORE_PATH.iterdir()
                if f.is_file()
                and f.suffix.lower() == f".{file_type}"
                and not f.name.startswith(".")
            ]

        else:
            files = [
                f.name
                for f in Config.DATASTORE_PATH.iterdir()
                if f.is_file() and not f.name.startswith(".")
            ]

        # Ensure geocoding-community-assets.csv is always included
        if "geocoding-community-assets.csv" not in files:
            files.append("geocoding-community-assets.csv")

        return files

    # Handle any exceptions that occur while accessing the datastore directory
    except Exception as e:
        print(
            f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error getting files:{Font_Colors.ENDC} {e}"
        )
        return []


def get_file_content(filename: str) -> Optional[str]:
    """
    Read content from a file in datastore.
    
    Args:
        filename (str): The name of the file to read.

    Returns:
        Optional[str]: The content of the file as a string, or None if the file does not exist or an error occurs.
    
    Raises:
        Exception: If there is an error reading the file.
    """
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


def get_db_connection():
    """
    Get a database connection from the connection pool.
    
    Returns:
        mysql.connector.connection.MySQLConnection: A connection object from the MySQL connection pool.
    """

    # Uncomment the line below to use a direct connection instead of a pool
    # return mysql.connector.connect(**Config.DB_CONFIG)

    # Use the connection pool to get a connection
    return db_pool.get_connection()


def json_query_results(query: str) -> Optional[Response]:
    """
    Execute a database query and return results as JSON.
    
    Args:
        query (str): The SQL query to execute.
    
    Returns:
        Optional[Response]: A Flask Response object containing the JSON results, or None if an error occurs.
    
    Raises:
        mysql.connector.Error: If there is an error executing the query or connecting to the database.
    """
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
    """
    Execute a database query and stream results as JSON.
    This function yields JSON strings for each row in the result set, allowing for efficient streaming of large datasets.
    
    Args:
        query (str): The SQL query to execute.
    
    Returns:
        Generator[str, None, None]: A generator that yields JSON strings for each row in the result set.
    
    Raises:
        mysql.connector.Error: If there is an error executing the query or connecting to the database.
    """

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
    """
    Execute a database query and return results as CSV in a StringIO object.
    
    Args:
        query (str): The SQL query to execute.
    
    Returns:
        Optional[io.StringIO]: A StringIO object containing the CSV results, or None if an error occurs.
    
    Raises:
        mysql.connector.Error: If there is an error executing the query or connecting to the database.
    """
    
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
    """
    Execute a database query and return results in the specified format.

    Args:
        query (str): The SQL query to execute.
        output_type (str): The format of the output. Can be "stream", "csv", "json", or "" (default is "json").
    
    Returns:
        Union[Generator[str, None, None], io.StringIO, Response]: The query results in the specified format.
    
    Raises:
        ValueError: If the output_type is not recognized.
    """

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
    """
    Generate a response from the Gemini model using the provided prompt and cache name.

    Args:
        prompt (str): The prompt to send to the Gemini model.
        cache_name (str): The name of the cache to use for the response.
        structured_response (bool): Whether to expect a structured response (default is False).

    Returns:
        str: The cleaned response text from the Gemini model.
    """
    try:
        model = Config.GEMINI_MODEL
        if structured_response:
            config = types.GenerateContentConfig(
                cached_content=cache_name if cache_name else None,
                response_schema=list[Structured_Data],
                response_mime_type="application/json",
            )
        else:
            config = types.GenerateContentConfig(
                cached_content=cache_name if cache_name else None
            )

        response = genai_client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

        raw_output = response.text.strip()
        cleaned_output = raw_output

        
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, dict):
                cleaned_output = parsed.get("response") or parsed.get("text") or raw_output
            elif isinstance(parsed, list) and all(isinstance(p, dict) and "response" in p for p in parsed):
                cleaned_output = "\n\n".join(p["response"] for p in parsed)
        except Exception:
            
            json_removal_patterns = [
                r',\s*"sender"\s*:\s*"[^"]*"\s*\}?\s*\]?\s*$',      # sender at end
                r',\s*"group"\s*:\s*"[^"]*"\s*\}?\s*\]?\s*$',       # group at end
                r',\s*"model"\s*:\s*"[^"]*"\s*\}?\s*\]?\s*$',       # model at end
                r'\}\s*\]$',                                        # closing object brackets
                r'"sender"\s*:\s*"[^"]*"',                          # inline sender
                r'"group"\s*:\s*"[^"]*"',                           # inline group
                r'"model"\s*:\s*"[^"]*"',                           # inline model
                r'"role"\s*:\s*"[^"]*"',                            # leaked role field
                r',?\s*\{[^{}]*\}\s*$',                             # trailing object
                r',?\s*\[?[^"\]]*"\]?\s*$',                         # malformed list ending
            ]

            for pattern in json_removal_patterns:
                cleaned_output = re.sub(pattern, '', cleaned_output, flags=re.DOTALL | re.IGNORECASE)

            
            cleaned_output = re.sub(r'[\s,;:.\\/\]\}"]+$', '', cleaned_output).strip()
            cleaned_output = re.sub(r'\s+', ' ', cleaned_output).strip()

        return cleaned_output if cleaned_output else raw_output

    except Exception as e:
        print(f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating response:{Font_Colors.ENDC} {e}")
        return f"{Font_Colors.FAIL}{Font_Colors.BOLD}✖ Error generating response:{Font_Colors.ENDC} {e}"


def create_gemini_context(
    context_request: str,
    preamble: str = "",
    generate_cache: bool = True,
    app_version: str = "",
    is_spatial: bool = False,
) -> Union[str, int, bool]:
    """
    Create a context for the Gemini model based on the specified request type and parameters.

    Args:
        context_request (str): The type of context request (e.g., "structured", "unstructured", "all", "experiment_5", "experiment_6", "experiment_7", "experiment_pit").
        preamble (str, optional): Additional preamble text to include in the context (default is an empty string).
        generate_cache (bool, optional): Whether to generate a cache for the context (default is True).
        app_version (str, optional): The application version to include in the cache name (default is an empty string).
        is_spatial (bool, optional): Whether to use spatial queries based on coordinates (default is False).
    
    Returns:
        Union[str, int, bool]: The name of the generated cache if generate_cache is True, or the total token count if generate_cache is False. Returns an error message if an exception occurs
    
    Raises:
        Exception: If there is an error generating the context or accessing files.
    """

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
        ):

            files_list = get_files("txt")
            query = build_311_query(
                data_request="311_summary_context", is_spatial=is_spatial
            )

            response = get_query_results(query=query, output_type="csv")

            content["parts"].append({"text": response.getvalue()})

            preamble_file = context_request + ".txt"

        # Read contents of found files
        for file in files_list:
            print("specific file", file)
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
    """
    Log an event to the database. 
    This function inserts a new log entry or updates an existing one based on the provided parameters.

    Args:
        session_id (str): The session ID for the event.
        app_version (str): The version of the application.
        data_selected (str, optional): Data selected for the event (default is an empty string).
        data_attributes (str, optional): Attributes of the data selected (default is an empty string).
        prompt_preamble (str, optional): Preamble for the prompt (default is an empty string).
        client_query (str, optional): The client's query (default is an empty string).
        app_response (str, optional): The application's response (default is an empty string).
        client_response_rating (str, optional): The client's response rating (default is an empty string).
        log_id (str, optional): The ID of the log entry to update (default is an empty string).
    
    Returns:
        Union[int, bool]: The ID of the log entry if successful, or False if there was an error.

    Raises:
        mysql.connector.Error: If there is an error connecting to the database or executing the query.
    """

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
    """
    Middleware to check if a session exists and create one if it doesn't.
    This function also logs the incoming request and handles CORS preflight requests.
    """
    # Handle CORS preflight requests
    if request.method == "OPTIONS":
        return ("", 204)

    rethinkai_api_client_key = request.headers.get("RethinkAI-API-Key")
    app_version = request.args.get("app_version", "")

    if (
        not rethinkai_api_client_key
        or rethinkai_api_client_key not in Config.RETHINKAI_API_KEYS
    ):
        return jsonify({"Error": "Invalid or missing API key"}), 401

    # Ensure session exists - NO LOGGING
    if "session_id" not in session:
        session.permanent = True
        session["session_id"] = str(uuid.uuid4())

    g.log_entry = None


#
# Endpoint Definitions
#
@app.route("/data/query", methods=["GET", "POST"])
def route_data_query():
    """
    Endpoint to handle data queries for 311 and 911 data.
    This endpoint supports both GET and POST requests. It builds SQL queries based on the request parameters
    and returns the results in the requested format (streaming, JSON, or CSV).

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access query parameters and session data.
    
    Returns:
        Response: A Flask Response object containing the query results in the requested format (streaming, JSON, or CSV).
    
    Raises:
        ValueError: If the output_type is not recognized or if required parameters are missing.
        Exception: If there is an error building the query or executing it against the database.
    """

    session_id = session.get("session_id")
    # Get query parameters
    app_version = request.args.get("app_version", "0")
    stream_result = request.args.get("stream", "False")
    request_zipcode = request.args.get("zipcode", "")
    event_ids = request.args.get("event_ids", "")
    request_date = request.args.get("date", "")
    data_request = request.args.get("request", "")
    output_type = request.args.get("output_type", "")
    is_spatial = request.args.get("is_spatial", "0") in ("true", "1", "yes")

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
                is_spatial=is_spatial,
            )

        elif data_request.startswith("911"):
            query = build_911_query(data_request=data_request, is_spatial=is_spatial)
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
            # log_event(
            #     session_id=session_id,
            #     app_version=app_version,
            #     log_id=g.log_entry,
            #     app_response="SUCCESS",
            # )
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
    """
    Endpoint to handle chat interactions with the Gemini model.
    This endpoint processes user messages, integrates geospatial data if available, and generates a response using the Gemini model.
    It also logs the interaction and returns the response along with any geospatial data if applicable.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access the request data and session information.
    
    Returns:
        Response: A Flask Response object containing the chat response in JSON format, including the session ID, the generated response, and any geospatial map data if available.
    
    Raises:
        Exception: If there is an error processing the user message, generating the response from the Gemini model, or logging the interaction.
    """

    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")
    is_spatial = request.args.get("is_spatial", "0") in ("true", "1", "yes")

    context_request = request.args.get(
        "context_request", request.args.get("request", "")
    )
    structured_response = request.args.get("structured_response", False)

    data = request.get_json()
    data_attributes = data.get("data_attributes", "")
    client_query = data.get("client_query", "")
    user_message = data.get("user_message", "")
    prompt_preamble = data.get("prompt_preamble", "")

    # GEOSPATIAL INTEGRATION - Keep your pipeline
    print("[GEOSPATIAL] incoming query:", user_message)
    geospatial_result = process_geospatial_message(
        user_message,
        Config.DATASTORE_PATH,
        Config.BASE_URL,
        Config.RETHINKAI_API_KEYS[0],
    )

    has_location = geospatial_result["map_data"] is not None
    map_data = geospatial_result["map_data"]

    # If we detected a location, use the enhanced prompt, otherwise use original
    if has_location:
        enhanced_query = geospatial_result["enhanced_prompt"]
    else:
        enhanced_query = client_query

    # data_selected, optional, list of files used when context_request==s
    cache_name = create_gemini_context(
        context_request=context_request,
        preamble=prompt_preamble,
        generate_cache=True,
        app_version=app_version,
        is_spatial=is_spatial,
    )

    full_prompt = f"User question: {enhanced_query}"

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
        try:
            raw_client_query = data.get("client_query", "")
            if raw_client_query:
                import json
                conversation = json.loads(raw_client_query)
                user_queries = [msg.get("text", "") for msg in conversation if msg.get("sender") == "user"]
                clean_client_query = json.dumps(user_queries)
            else:
                clean_client_query = user_message
        except:
            clean_client_query = user_message

        log_id = log_event(
            session_id=session_id,
            app_version=app_version,
            data_selected=context_request,
            data_attributes=data_attributes,
            prompt_preamble=prompt_preamble,
            client_query=clean_client_query,  
            app_response=app_response,
        )

        response = {
            "session_id": session_id,
            "response": app_response,
            "log_id": log_id,
        }

        # GEOSPATIAL INTEGRATION - Include map data in response
        if map_data:
            response["mapData"] = map_data

        if hasattr(g, 'log_entry') and g.log_entry:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
        return jsonify(response)

    # Handle exceptions and log errors
    except Exception as e:
        if hasattr(g, 'log_entry') and g.log_entry:
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
    """
    Endpoint to handle context cache management for the chat application.
    This endpoint allows users to create, clear, or retrieve context caches based on the specified request parameters.
    It supports both GET and POST requests, where GET requests can return the list of existing context caches or the token count for a specific context request,
    and POST requests can create a new context cache or clear existing caches.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access the request data and session information.
    
    Returns:
        Response: A Flask Response object containing the context cache information in JSON format.
    
    Raises:
        400 Bad Request: If the required parameters are missing or invalid.
        500 Internal Server Error: If there is an error generating the context cache or retrieving the token count.
    """

    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")
    is_spatial = request.args.get("is_spatial", "0") in ("true", "1", "yes")

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
                is_spatial=is_spatial,
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
                is_spatial=is_spatial,
            )

            return jsonify(response)


@app.route("/chat/summary", methods=["POST"])
def chat_summary():
    """
    Endpoint to summarize a chat conversation.
    This endpoint takes a list of messages from the chat, constructs a chat transcript, and generates a summary using the Gemini model.
    It reads a predefined prompt from a file and combines it with the chat transcript to form the full prompt for the model.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request object to access the request data.

    Returns:
        Response: A Flask Response object containing the summary of the chat conversation in JSON format.
    
    Raises:
        400 Bad Request: If no messages are provided in the request.
        404 Not Found: If the summary prompt file is not found.
        500 Internal Server Error: If there is an error reading the summary prompt file or generating the summary.
    """

    data = request.get_json()
    messages = data.get("messages", [])

    if not messages:
        return jsonify({"error": "No messages provided."}), 400

    # Create chat_transcript from messages
    chat_transcript = "\n".join(
        f"{'User' if msg['sender'] == 'user' else 'Chat'}: {msg['text']}"
        for msg in messages
    )

    summary_file_path = "./prompts/get_summary.txt"

    # Read the content from the get_summary.txt file
    try:
        with open(summary_file_path, "r") as file:
            file_content = file.read()

        # Combine the file content with the chat transcript to form the full prompt
        full_prompt = f"{file_content}\n{chat_transcript}"

    except FileNotFoundError:
        return jsonify({"error": "Summary prompt not found."}), 404
    except Exception as e:
        print(f"✖ Error reading summary prompt file: {e}")
        return jsonify({"error": str(e)}), 500

    # Call the Gemini response function with the combined full_prompt
    try:
        summary = get_gemini_response(prompt=full_prompt, cache_name=None)
        return jsonify({"summary": summary})

    except Exception as e:
        print(f"✖ Error summarizing chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/chat/identify_places", methods=["POST"])
def identify_places():
    """
    Endpoint to identify places from a user message.
    This endpoint takes a user message, reads a predefined prompt from a file, and generates a response using the Gemini model.
    It combines the content of the prompt file with the user message to form the full prompt for the model.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request object to access the request data.
    
    Returns:
        Response: A Flask Response object containing the identified places in JSON format.
    
    Raises:
        400 Bad Request: If no message is provided in the request.
        404 Not Found: If the identify_places prompt file is not found.
        500 Internal Server Error: If there is an error reading the prompt file or generating the response.
    """
    
    data = request.get_json()
    message = data.get("message", [])

    if not message:
        return jsonify({"error": "No message provided."}), 400

    prompt_file_path = "./prompts/identify_places.txt"

    # Read the content from identify_places.txt
    try:
        with open(prompt_file_path, "r", encoding="utf-8") as file:
            file_content = file.read()

        # Combine the file content with the message to form the full prompt
        full_prompt = f"{file_content}\n{message}"

    except FileNotFoundError:
        return jsonify({"error": "Prompt file not found."}), 404
    except Exception as e:
        print(f"✖ Error reading prompt file: {e}")
        return jsonify({"error": str(e)}), 500

    # Call the Gemini response function with the combined full_prompt
    try:
        places = get_gemini_response(prompt=full_prompt, cache_name=None)
        return jsonify(places)

    except Exception as e:
        print(f"✖ Error identifying places: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/log", methods=["POST", "PUT"])
def route_log():
    """
    Endpoint to log events related to user interactions with the application.
    This endpoint supports both POST and PUT requests.
    - POST requests create a new log entry.
    - PUT requests update an existing log entry based on the provided log_id.
    The log entry includes details such as session ID, app version, data selected, data attributes, prompt preamble, client query, app response, and client response rating.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access the request data and session information.
    
    Returns:
        Response: A Flask Response object containing a success message and the log ID if the log entry is created or updated successfully.
    
    Raises:
        400 Bad Request: If required parameters are missing or invalid.
        500 Internal Server Error: If there is an error creating or updating the log entry.
    """
    
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
    """
    Endpoint to retrieve a summary for a specific month.
    This endpoint accepts a month parameter and returns the summary for that month.
    If the month is not provided or if no summary is available for the specified month, it returns an error response.
    The summary is fetched from the llm_summaries table in the database.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access the request data and session information.
    
    Returns:
        Response: A Flask Response object containing the summary for the specified month in JSON format.
    
    Raises:
        400 Bad Request: If the month parameter is missing or invalid.
        404 Not Found: If no summary is available for the specified month.
        500 Internal Server Error: If there is an error accessing the database or fetching the summary.
    """

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
    """
    Endpoint to retrieve all LLM summaries.
    This endpoint fetches all summaries from the llm_summaries table in the database and returns them in JSON format.
    It logs the request and handles any errors that may occur during the database query.

    Args:
        None: This function does not take any parameters directly, but uses Flask's request and session objects to access the request data and session information.
    
    Returns:
        Response: A Flask Response object containing all summaries in JSON format.
    
    Raises:
        500 Internal Server Error: If there is an error accessing the database or fetching the summaries
    """

    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.exebefore_requestcute(
            "SELECT month_label, summary FROM llm_summaries ORDER BY month_label ASC"
        )
        rows = cursor.fetchall()

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

# Main entry point to run the Flask application
if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
