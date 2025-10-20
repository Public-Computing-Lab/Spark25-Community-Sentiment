# test.py
from sqlalchemy import create_engine, text

# Your connection string
DB_URL = "postgresql://dorchester_db_user:6CiTHuq3z1aC8gSokVr560LX7qiF7CtW@dpg-d3pcedggjchc73aff580-a.ohio-postgres.render.com/dorchester_db"

# Create the engine
engine = create_engine(DB_URL)

def test_connection():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT NOW();"))
            print("✅ Database connection successful!")
            print("Current time on server:", result.scalar())
    except Exception as e:
        print("❌ Database connection failed:")
        print(e)

def list_tables():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema='public';
            """))
            tables = [row[0] for row in result]
            print("📋 Tables in database:", tables)
    except Exception as e:
        print("❌ Could not fetch tables:")
        print(e)

def preview_data(table_name):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 5;"))
            rows = result.fetchall()
            print(f"🔍 Preview of table '{table_name}':")
            print("Something")
            print(rows)
            for row in rows:
                print("SOmething")
                print(row)
    except Exception as e:
        print(f"❌ Could not preview data from '{table_name}':")
        print(e)

if __name__ == "__main__":
    test_connection()
    list_tables()
    # Uncomment and edit this line to preview a specific table
    preview_data("Dorchester_Person_Shot")
