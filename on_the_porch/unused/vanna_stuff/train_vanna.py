#!/usr/bin/env python3
"""
Minimal training script for Vanna using Gemini from .env.
Reflects the live Postgres schema via SQLAlchemy and trains Vanna with
concise documentation of tables and columns.
"""

from typing import List
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

from vanna.chromadb import ChromaDB_VectorStore
from vanna.openai import OpenAI_Chat
import os

class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')
        
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config={'api_key': OPENAI_API_KEY, 'model': OPENAI_MODEL})


# Clear all GEMINI and GOOGLE environment variables first
# for key in list(os.environ.keys()):
#     if key.startswith('GEMINI_') or key.startswith('GOOGLE_'):
#         del os.environ[key]

# Load environment variables from .env file
load_dotenv()

POSTGRES_HOST = 'dpg-d3g661u3jp1c73eg9v1g-a.ohio-postgres.render.com'
POSTGRES_DB = 'crime_rate_h3u5'
POSTGRES_USER = 'user1'
POSTGRES_PASSWORD = 'BbWTihWnsBHglVpeKK8XfQgEPDOcokZZ'
POSTGRES_PORT = 5432

# Get Gemini credentials from .env
# GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')  # Fallback to hardcoded key
# GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'models/gemini-2.0-flash-001')  # Default model
# Get OpenAI credentials from .env
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4')


def build_schema_documentation() -> str:
    url = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    engine = create_engine(url)
    inspector = inspect(engine)
    table_names: List[str] = inspector.get_table_names(schema='public')

    if not table_names:
        return "No tables found in schema 'public'."

    parts: List[str] = []
    parts.append("Database schema overview (schema: public):")
    for table_name in table_names:
        columns = inspector.get_columns(table_name, schema='public')
        parts.append(f"\nTable {table_name}:")
        for col in columns:
            col_name = col.get('name')
            col_type = str(col.get('type'))
            nullable = col.get('nullable', True)
            parts.append(f"- {col_name}: {col_type} {'NULL' if nullable else 'NOT NULL'}")

    return "\n".join(parts)


def build_crimes311_documentation() -> str:
    return (
        "Boston 311 service request dataset (table: crimes311).\n\n"
        "Key columns and meaning:\n"
        "- case_enquiry_id: Unique identifier for each service request.\n"
        "- open_dt: Timestamp when the case was opened.\n"
        "- sla_target_dt: Target resolution timestamp per SLA.\n"
        "- closed_dt: Timestamp when the case was closed (if closed).\n"
        "- on_time: Whether closed before SLA target (e.g., ONTIME/OVERDUE).\n"
        "- case_status: Current status (e.g., Open, Closed).\n"
        "- closure_reason: Short text on why/how the case was closed.\n"
        "- case_title: Brief title of the request.\n"
        "- subject: Department domain (e.g., Transportation - Traffic Division).\n"
        "- reason: High-level reason/category.\n"
        "- type: Specific type (e.g., Abandoned Vehicles).\n"
        "- queue: Workflow queue name.\n"
        "- department: Handling department.\n"
        "- submitted_photo / closed_photo: URLs or flags for photos (if present).\n"
        "- location: Human-readable address string.\n"
        "- fire_district, pwd_district, city_council_district, police_district: District identifiers.\n"
        "- neighborhood / neighborhood_services_district: Neighborhood fields.\n"
        "- ward / precinct: Political and policing subdivisions.\n"
        "- location_street_name / location_zipcode: Address components.\n"
        "- latitude / longitude: WGS84 coordinates.\n"
        "- geom_4326: Geometry point in EPSG:4326.\n"
        "- source: Submission source (e.g., Citizens Connect App).\n\n"
        "Typical queries:\n"
        "- Count requests by type, neighborhood, or department.\n"
        "- Find overdue vs on-time cases by date range.\n"
        "- Show recent requests near a location using latitude/longitude.\n"
    )


def _make_sqlalchemy_url() -> str:
    return (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )


def _table_has_columns(inspector, table_name: str, required_columns: List[str]) -> bool:
    existing = {c.get('name') for c in inspector.get_columns(table_name, schema='public')}
    return all(col in existing for col in required_columns)


def build_question_sql_pairs() -> List[dict]:
    url = _make_sqlalchemy_url()
    engine = create_engine(url)
    inspector = inspect(engine)
    tables = inspector.get_table_names(schema='public')

    pairs: List[dict] = []

    crimes_table = 'crimes311'
    if crimes_table in tables:
        # 1) Total requests
        if _table_has_columns(inspector, crimes_table, []):
            pairs.append({
                'question': 'How many 311 requests are there in total?',
                'sql': f'SELECT COUNT(*) AS total_requests FROM {crimes_table};'
            })

        # 2) Top request types
        if _table_has_columns(inspector, crimes_table, ['type']):
            pairs.append({
                'question': 'What are the top 10 request types by count?',
                'sql': (
                    f"SELECT type, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"GROUP BY type ORDER BY request_count DESC LIMIT 10;"
                )
            })

        # 3) Requests by neighborhood
        if _table_has_columns(inspector, crimes_table, ['neighborhood']):
            pairs.append({
                'question': 'Show request counts by neighborhood, highest first.',
                'sql': (
                    f"SELECT neighborhood, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"GROUP BY neighborhood ORDER BY request_count DESC;"
                )
            })

        # 4) Overdue vs on-time in 2025
        if _table_has_columns(inspector, crimes_table, ['on_time', 'open_dt']):
            pairs.append({
                'question': 'How many requests were on-time vs overdue in 2025?',
                'sql': (
                    f"SELECT on_time, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"WHERE open_dt >= '2025-01-01' AND open_dt < '2026-01-01' "
                    f"GROUP BY on_time ORDER BY request_count DESC;"
                )
            })

        # 5) Average closure time in days by type
        if _table_has_columns(inspector, crimes_table, ['open_dt', 'closed_dt', 'type']):
            pairs.append({
                'question': 'What is the average closure time in days by request type?',
                'sql': (
                    f"SELECT type, "
                    f"AVG(EXTRACT(EPOCH FROM (closed_dt - open_dt)))/86400.0 AS avg_days_to_close "
                    f"FROM {crimes_table} "
                    f"WHERE closed_dt IS NOT NULL AND open_dt IS NOT NULL "
                    f"GROUP BY type ORDER BY avg_days_to_close;"
                )
            })

        # 6) Recent closed requests in Dorchester
        if _table_has_columns(inspector, crimes_table, ['neighborhood', 'closed_dt', 'case_title', 'case_status']):
            pairs.append({
                'question': 'Show the 10 most recent closed requests in Dorchester.',
                'sql': (
                    f"SELECT case_title, case_status, closed_dt "
                    f"FROM {crimes_table} "
                    f"WHERE neighborhood = 'Dorchester' AND closed_dt IS NOT NULL "
                    f"ORDER BY closed_dt DESC LIMIT 10;"
                )
            })

        # 7) Requests by police district
        if _table_has_columns(inspector, crimes_table, ['police_district']):
            pairs.append({
                'question': 'Break down request counts by police district.',
                'sql': (
                    f"SELECT police_district, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"GROUP BY police_district ORDER BY request_count DESC;"
                )
            })

        # 8) Requests by zipcode
        if _table_has_columns(inspector, crimes_table, ['location_zipcode']):
            pairs.append({
                'question': 'Which zipcodes have the most 311 requests?',
                'sql': (
                    f"SELECT location_zipcode::text AS zipcode, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"GROUP BY location_zipcode ORDER BY request_count DESC;"
                )
            })

        # 9) Requests near a point (bounding box) if lat/lon exist
        if _table_has_columns(inspector, crimes_table, ['latitude', 'longitude']):
            pairs.append({
                'question': 'Show requests within ~0.01 degrees of 42.30,-71.06 (approx. 1 km).',
                'sql': (
                    f"SELECT * FROM {crimes_table} "
                    f"WHERE latitude BETWEEN 42.29 AND 42.31 "
                    f"AND longitude BETWEEN -71.07 AND -71.05 "
                    f"ORDER BY open_dt DESC LIMIT 50;"
                )
            })

        # 10) Open vs Closed by department
        if _table_has_columns(inspector, crimes_table, ['department', 'case_status']):
            pairs.append({
                'question': 'Open vs closed counts by department.',
                'sql': (
                    f"SELECT department, case_status, COUNT(*) AS request_count "
                    f"FROM {crimes_table} "
                    f"GROUP BY department, case_status ORDER BY department, case_status;"
                )
            })

    return pairs


def main():
    print("Reflecting schema from PostgreSQL...")
    schema_doc = build_schema_documentation()
    print("Schema reflection completed")

    # Debug: Check what's being loaded
    print(f"DEBUG: OPENAI_API_KEY = {OPENAI_API_KEY}")
    print(f"DEBUG: OPENAI_MODEL = {OPENAI_MODEL}")
    
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not found in .env file")

    vn = MyVanna()

    vn.connect_to_postgres(
        host=POSTGRES_HOST,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        port=POSTGRES_PORT
    )
    print("Connected to PostgreSQL for training")

    print("Training Vanna with schema documentation...")
    vn.train(documentation=schema_doc)
    vn.train(documentation=build_crimes311_documentation())

    # Add dynamic question-SQL pairs based on schema
    pairs = build_question_sql_pairs()
    print(f"Adding {len(pairs)} question-SQL training pairs...")
    for p in pairs:
        vn.train(question=p['question'], sql=p['sql'])

    print("Training complete")


if __name__ == '__main__':
    main()


