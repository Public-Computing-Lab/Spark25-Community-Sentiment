#!/usr/bin/env python3
"""
Check the actual database schema to see what columns exist.
Reads DATABASE_URL from env or .env.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def check_table_schema():
    try:
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set. Add it to your environment or .env file.")

        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema='public';
                """
            ))
            tables = [row[0] for row in result]
            print("📋 Tables in database:", tables)

            for table in tables:
                print(f"\n🔍 Columns in table '{table}':")
                result = conn.execute(text(
                    f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = '{table}' AND table_schema = 'public'
                    ORDER BY ordinal_position;
                    """
                ))
                columns = result.fetchall()
                for col in columns:
                    print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")

    except Exception as e:
        print("❌ Could not check schema:")
        print(e)


if __name__ == "__main__":
    check_table_schema()
