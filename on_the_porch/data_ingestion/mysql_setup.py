"""
Minimal MySQL setup for the ingestion pipeline.

- Creates database: rethink_ai_boston  (if it doesn't exist)
- Creates table: weekly_events         (drops/recreates it)

Adjust MYSQL_* values as needed.
"""

import pymysql
import os

import dotenv
dotenv.load_dotenv()

MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")


def create_database():
    print(f"Creating database: {MYSQL_DB}")
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        print(f"✓ Database '{MYSQL_DB}' created/verified")
    finally:
        conn.close()


def create_weekly_events_table():
    print(f"Creating table: weekly_events")
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        charset="utf8mb4",
        autocommit=True,
    )
    ddl = """
    DROP TABLE IF EXISTS weekly_events;
    CREATE TABLE weekly_events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source_pdf VARCHAR(255) NULL,
        page_number INT NULL,
        event_name VARCHAR(255) NOT NULL,
        event_date VARCHAR(255) NOT NULL,
        start_date DATE NULL,
        end_date DATE NULL,
        start_time TIME NULL,
        end_time TIME NULL,
        raw_text TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    try:
        with conn.cursor() as cur:
            for stmt in ddl.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        print("✓ Table 'weekly_events' created")
    finally:
        conn.close()


if __name__ == "__main__":
    print("MySQL Setup Script")
    print("=" * 50)
    if not MYSQL_USER or not MYSQL_PASSWORD or not MYSQL_DB:
        print("ERROR: Missing MySQL credentials in .env file")
        print(f"  MYSQL_USER: {MYSQL_USER or 'NOT SET'}")
        print(f"  MYSQL_PASSWORD: {'SET' if MYSQL_PASSWORD else 'NOT SET'}")
        print(f"  MYSQL_DB: {MYSQL_DB or 'NOT SET'}")
        exit(1)
    
    try:
        create_database()
        create_weekly_events_table()
        print("=" * 50)
        print("✓ Setup complete!")
    except Exception as e:
        print(f"✗ Error: {e}")
        exit(1)