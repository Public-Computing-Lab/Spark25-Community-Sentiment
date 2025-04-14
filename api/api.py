from flask import Flask, request, jsonify, g, session, Response, stream_with_context
import csv
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pathlib import Path
from typing import List, Dict, Union, Optional, Any, Generator
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
import datetime
import os
import re
import io
import uuid
import asyncio
import json
import decimal

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).parent


# Configuration constants
class Config:
    API_VERSION = "API v 0.3.1"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL")
    GEMINI_CACHE_TTL = int(os.getenv("GEMINI_CACHE_TTL", "7"))
    HOST = os.getenv("API_HOST")
    PORT = os.getenv("API_PORT")
    DATASTORE_PATH = BASE_DIR / Path(os.getenv("DATASTORE_PATH", ".").lstrip("./"))
    PROMPTS_PATH = BASE_DIR / Path(os.getenv("PROMPTS_PATH", ".").lstrip("./"))
    ALLOWED_EXTENSIONS = {"csv", "txt"}
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "rethinkAI2025!")
    FLASK_SESSION_COOKIE_SECURE = os.getenv("FLASK_SESSION_COOKIE_SECURE", "False").lower() == "true"

    # Database configuration
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }


#
# SQL Query Constants
#
class SQLConstants:
    # 311 category mappings
    CATEGORY_TYPES = {
        "living_conditions": "'Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential'",
        "trash": "'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping'",
        "streets": "'Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair'",
        "parking": "'Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints'",
    }

    # Set the 'all' category to include all individual categories
    CATEGORY_TYPES["all"] = ", ".join([cat for cat in ", ".join(CATEGORY_TYPES.values()).split(", ")])

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
    COUNT(*) AS total_year,
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
    BOS311_BASE_WHERE = "police_district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester'"

    # 911 specific constants
    BOS911_BASE_WHERE = "district IN ('B2', 'B3', 'C11') AND neighborhood = 'Dorchester' AND year >= 2018 AND year < 2025"


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
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def get_files(file_type: Optional[str] = None, specific_files: Optional[List[str]] = None) -> List[str]:
    """Get a list of files from the datastore directory."""
    try:
        if not Config.DATASTORE_PATH.exists():
            return []

        if specific_files:
            return [f.name for f in Config.DATASTORE_PATH.iterdir() if f.is_file() and f.name in specific_files and not f.name.startswith(".")]

        if file_type:
            return [f.name for f in Config.DATASTORE_PATH.iterdir() if f.is_file() and f.suffix.lower() == f".{file_type}" and not f.name.startswith(".")]

        return [f.name for f in Config.DATASTORE_PATH.iterdir() if f.is_file() and not f.name.startswith(".")]

    except Exception as e:
        print(f"Error getting files: {e}")
        return []


def get_file_content(filename: str) -> Optional[str]:
    """Read content from a file in the datastore."""
    try:
        file_path = Config.DATASTORE_PATH / filename
        if not file_path.exists():
            return None

        return file_path.read_text(encoding="utf-8")

    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return None


# DB Connection
def get_db_connection():
    # return mysql.connector.connect(**Config.DB_CONFIG)
    return db_pool.get_connection()


# Send prompt to Gemini
async def get_gemini_response(prompt: str, cache_name: str) -> str:
    """Sends the prompt to Google Gemini and returns the response."""
    try:
        model = Config.GEMINI_MODEL
        response = await asyncio.to_thread(
            lambda: genai_client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(cached_content=cache_name),
            )
        )
        # print(f"\n✅ Gemini Response: {response.text}")
        return response.text
    except Exception as e:
        print(f"❌ Error generating response: {e}")
        return f"❌ Error generating response: {e}"


# TODO: Unsure if this should be async as well
def create_gemini_context(context_request: str, files: str = "", preamble: str = "", generate_cache: bool = True, app_version: str = "") -> Union[str, int, bool]:
    # test if cache exists
    if generate_cache:
        for cache in genai_client.caches.list():
            if cache.display_name == context_request + "_" + app_version:
                return cache.name

    try:
        content = {"parts": []}

        if context_request == "structured":
            files_list = get_files("csv")
        elif context_request == "unstructured":
            files_list = get_files("txt")
        elif context_request == "all":
            files_list = get_files()
        elif context_request == "specific":
            if not files:
                return False
            specific_files = [f.strip() for f in files.split(",")]
            files_list = get_files(specific_files=specific_files)
        elif context_request == "experiment_5" or context_request == "experiment_6":
            files_list = get_files("txt")
            query = build_summary_query()

            try:
                conn = get_db_connection()
                with conn.cursor(dictionary=True) as cursor:

                    cursor.execute(query)
                    fieldnames = [desc[0] for desc in cursor.description]

                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()

                    for row in cursor:
                        writer.writerow(row)

                    content["parts"].append({"text": output.getvalue()})

            except mysql.connector.Error as err:
                print(f"Database error: {str(err)}")
                return None

            finally:
                if "conn" in locals():
                    cursor.close()
                    conn.close()

        preamble_file = context_request + ".txt"
        # Read contents of found files
        for file in files_list:
            file_content = get_file_content(file)
            if file_content is not None:
                content["parts"].append({"text": file_content})

        # Read prompt preamble
        if context_request != "specific":
            path = Config.PROMPTS_PATH / preamble_file
            if not path.is_file():
                raise FileNotFoundError(f"File not found: {path}")
            system_prompt = path.read_text(encoding="utf-8")
        else:
            system_prompt = preamble

        display_name = context_request + "_" + app_version

        # Generate cache or return token count
        if generate_cache:
            # Set cache expiration time
            cache_ttl = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=Config.GEMINI_CACHE_TTL)).isoformat().replace("+00:00", "Z")

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
            print(f"Conxtex display name: {display_name}")
            content["parts"].append({"text": system_prompt})
            total_tokens = genai_client.models.count_tokens(model=Config.GEMINI_MODEL, contents=content["parts"])
            return total_tokens.total_tokens

    except Exception as e:
        print(f"❌ Error generating context: {e}")
        return f"❌ Error generating context: {e}"


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
        print(f"Database error: {str(err)}")
        return False

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


# DB Query
def return_query_results(query: str) -> Optional[List[Dict[str, Any]]]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(query)
        result = cursor.fetchall()

        return result if result else None

    except mysql.connector.Error as err:
        print(f"Database error: {str(err)}")
        return None

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


def stream_query_results(query: str) -> Generator[str]:
    conn = None
    cursor = None

    try:
        conn = get_db_connection()

        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        # Stream the results
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
                if hasattr(value, "isoformat"):  # Check if it has isoformat method (datetime objects do)
                    processed_row[key] = value.isoformat()
                elif isinstance(value, decimal.Decimal):  # Handle Decimal objects
                    processed_row[key] = float(value)
                else:
                    processed_row[key] = value

            yield json.dumps(processed_row)

        # Close the JSON structure
        yield "\n]"

    except mysql.connector.Error as err:
        # Handle database errors
        yield json.dumps({"error": f"Database error: {str(err)}"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
    if data_request == "311_by_geo":
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
    elif data_request == "311_summary" and event_ids:
        query = f"""
        SELECT
            CASE
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
            END AS reported_issue,
            COUNT(*) AS total
        FROM
            bos311_data
        WHERE
            id IN ({event_ids})
        GROUP BY reported_issue
        """
        print(query)
        return query
    elif data_request == "311_summary" and request_date:
        query = f"""
        SELECT
            CASE
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
            END AS reported_issue,
            COUNT(*) AS total
        FROM
            bos311_data
        WHERE
            DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'
            AND type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY reported_issue
        """
        return query
    elif data_request == "311_summary" and not request_date and not event_ids:
        query = f"""
        SELECT
            CASE
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']}) THEN 'Living Conditions'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['trash']}) THEN 'Trash, Recycling, And Waste'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['streets']}) THEN 'Streets, Sidewalks, And Parks'
                WHEN type IN ({SQLConstants.CATEGORY_TYPES['parking']}) THEN 'Parking'
            END AS reported_issue,
            COUNT(*) AS total
        FROM
            bos311_data
        WHERE            
            type IN ({SQLConstants.CATEGORY_TYPES[request_options]})
            AND {SQLConstants.BOS311_BASE_WHERE}
        GROUP BY reported_issue
        """
        return query
    else:
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


def build_summary_query():
    return f"""
    WITH incident_data AS (
    SELECT
        year,
        '911 Shot Fired Confirmed' AS incident_type,
        quarter,
        month
    FROM shots_fired_data
    WHERE
    {SQLConstants.BOS911_BASE_WHERE}
    AND ballistics_evidence = 1
    UNION ALL
    SELECT
        year,
        '911 Shot Fired Unconfirmed' AS incident_type,
        quarter,
        month
    FROM shots_fired_data
    WHERE
    {SQLConstants.BOS911_BASE_WHERE}
    AND ballistics_evidence = 0
    UNION ALL
    SELECT
        year,
        '911 Homicides' AS incident_type,
        quarter,
        month
    FROM homicide_data
    WHERE
    {SQLConstants.BOS911_BASE_WHERE}
    UNION ALL
    SELECT
        YEAR(open_dt) AS year,
        '311 Trash/Dumping Issues' AS incident_type,
        QUARTER(open_dt) AS quarter,
        MONTH(open_dt) AS month
    FROM bos311_data
    WHERE
    type IN ({SQLConstants.CATEGORY_TYPES['trash']})
    AND {SQLConstants.BOS311_BASE_WHERE}
    UNION ALL
    SELECT
        YEAR(open_dt) AS year,
        '311 Living Condition Issues' AS incident_type,
        QUARTER(open_dt) AS quarter,
        MONTH(open_dt) AS month
    FROM bos311_data
    WHERE
    type IN ({SQLConstants.CATEGORY_TYPES['living_conditions']})
    AND {SQLConstants.BOS311_BASE_WHERE}
    UNION ALL
    SELECT
        YEAR(open_dt) AS year,
        '311 Streets Issues' AS incident_type,
        QUARTER(open_dt) AS quarter,
        MONTH(open_dt) AS month
    FROM bos311_data
    WHERE
    type IN ({SQLConstants.CATEGORY_TYPES['streets']})
    AND {SQLConstants.BOS311_BASE_WHERE}
    UNION ALL
    SELECT
        YEAR(open_dt) AS year,
        '311 Parking Issues' AS incident_type,
        QUARTER(open_dt) AS quarter,
        MONTH(open_dt) AS month
    FROM bos311_data
    WHERE
    type IN ({SQLConstants.CATEGORY_TYPES['parking']})
    AND {SQLConstants.BOS311_BASE_WHERE}
    )
    SELECT
        year,
        incident_type,
        {SQLConstants.BOS911_TIME_BREAKDOWN}
    FROM incident_data
    GROUP BY year, incident_type
    ORDER BY year, incident_type
    """


#
# Middleware to check session and create if needed
#
@app.before_request
def check_session():
    if "session_id" not in session:
        session.permanent = True  # Make the session persistent
        session["session_id"] = str(uuid.uuid4())
        log_event(
            session_id=session["session_id"],
            app_version="0.2",
            data_attributes=Config.API_VERSION,
            app_response="New session created",
        )

    # Log the request
    g.log_entry = log_event(
        session_id=session["session_id"],
        app_version="0.2",
        data_attributes=Config.API_VERSION,
        client_query=f"Request: [{request.method}] {request.url}",
    )


#
# Endpoint Definitions
#
@app.route("/data/query", methods=["GET"])
def route_data_query():
    session_id = session.get("session_id")
    # Get query parameters
    app_version = request.args.get("app_version", "0")
    stream_result = request.args.get("stream", "False")
    request_zipcode = request.args.get("zipcode", "")
    event_ids = request.args.get("event_ids", "")
    request_date = request.args.get("date", "")

    try:
        # Get and validate request parameters
        data_request = request.args.get("request", "")
        if not data_request:
            return jsonify({"error": "Missing data_request parameter"}), 400

        request_options = request.args.get("category", "")
        if data_request.startswith("311_by") and not request_options:
            return (
                jsonify({"error": "Missing required options parameter for 311 request"}),
                400,
            )

        if data_request.startswith("311_on_date") and not request_date:
            return (
                jsonify({"error": "Missing required options parameter for 311 request"}),
                400,
            )

        # Validate date format for date-specific queries
        if data_request.startswith("311_on_date") and not check_date_format(request_date):
            return jsonify({"error": 'Incorrect date format. Expects "YYYY-MM"'}), 400

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
            return jsonify({"error": "Invalid data_request parameter"}), 400

        if not query:
            return jsonify({"error": "Failed to build query"}), 500

        # Return w/ streaming
        if stream_result == "True":
            return Response(stream_with_context(stream_query_results(query=query)), mimetype="application/json")
        # Return bulk result
        else:
            result = return_query_results(query=query)

            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="SUCCESS",
            )
            return jsonify(result)

    except Exception as e:
        log_event(
            session_id=session_id,
            app_version=app_version,
            log_id=g.log_entry,
            app_response=f"ERROR: {str(e)}",
        )
        return jsonify({"error": str(e)}), 500


@app.route("/chat", methods=["POST"])
def route_chat():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    context_request = request.args.get("context_request", request.args.get("request", ""))

    data = request.get_json()

    # Extract chat data parameters
    data_selected = data.get("data_selected", "")
    data_attributes = data.get("data_attributes", "")
    client_query = data.get("client_query", "")
    prompt_preamble = data.get("prompt_preamble", "")

    # data_selected, optional, list of files used when context_request==s
    cache_name = create_gemini_context(
        context_request=context_request,
        files=data_selected,
        preamble=prompt_preamble,
        generate_cache=True,
        app_version=app_version,
    )

    full_prompt = f"User question: {client_query}"

    # Process chat
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app_response = loop.run_until_complete(get_gemini_response(full_prompt, cache_name))
        if "❌ Error" in app_response:
            print(f"❌ ERROR from Gemini API: {app_response}")
            return jsonify({"error": app_response}), 500

        # Log the interaction
        log_id = log_event(
            session_id=session_id,
            app_version=app_version,
            data_selected=context_request + " " + data_selected,
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
        print(f"❌ Exception in /chat: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500


@app.route("/chat/context", methods=["GET", "POST"])
def route_chat_context():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")

    context_request = request.args.get("context_request", request.args.get("request", ""))

    if request.method == "GET":
        # return list of context caches if <request> is ""
        if not context_request:
            response = {cache.name: str(cache) for cache in genai_client.caches.list()}
            return jsonify(response)

        else:
            # test token count for context cache of <request>
            token_count = create_gemini_context(
                context_request=context_request,
                files="",
                preamble="",
                generate_cache=False,
                app_version=app_version,
            )

            if isinstance(token_count, int):
                return jsonify({"token_count": token_count})
            elif hasattr(token_count, "total_tokens") and isinstance(token_count.total_tokens, int):
                return jsonify({"token_count": token_count.total_tokens})
            else:
                # Handle the error appropriately, e.g., log the error and return an error response
                print(f"Error getting token count: {token_count}")  # Log the error
                return (
                    jsonify({"error": "Failed to get token count"}),
                    500,
                )  # Return an error response
    if request.method == "POST":
        # TODO: implement 'specific' context_request with list of files from datastore
        # FOR NOW: assumes 'structured', 'unstructured', 'all', 'experiment_5' context_request
        # Context cache creation appends app_version so caches are versioned.
        if not context_request:
            return jsonify({"error": "Missing context_request parameter"}), 400

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
            data_selected = data.get("data_selected", "")
            prompt_preamble = data.get("prompt_preamble", "")

            response = create_gemini_context(
                context_request=context_request,
                files=data_selected,
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
                jsonify({"message": "Log entry created successfully", "log_id": log_id}),
                201,
            )
        else:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="ERROR: Log entry not created",
            )
            return jsonify({"error": "Failed to create log entry"}), 500
    if request.method == "PUT":
        if not data.get("log_id", ""):
            return jsonify({"error": "Missing log_id to update"}), 500

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
                jsonify({"message": "Log entry updated successfully", "log_id": log_id}),
                201,
            )
        else:
            log_event(
                session_id=session_id,
                app_version=app_version,
                log_id=g.log_entry,
                app_response="ERROR: Log entry not updated",
            )
            return jsonify({"error": "Failed to update log entry"}), 500


@app.route("/llm_summaries", methods=["GET"])
def route_llm_summary():
    session_id = session.get("session_id")
    app_version = request.args.get("app_version", "0")
    month = request.args.get("month", request.args.get("date", ""))

    if not month:
        return jsonify({"error"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT summary FROM llm_summaries WHERE month_label = %s", (month,))
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
        return jsonify({"error": str(e)}), 500

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
        cursor.execute("SELECT month_label, summary FROM llm_summaries ORDER BY month_label ASC")
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
        return jsonify({"error": str(e)}), 500

    finally:
        if "conn" in locals():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
