import pandas as pd
import sqlite3
from sqlalchemy import create_engine

# Paths
csv_file = 'data/Dorchester_311.csv'
db_file = 'data/dorchester_311.db'

# Create SQLite database and load CSV
print(f"Loading {csv_file}...")
engine = create_engine(f'sqlite:///{db_file}')

# Read CSV in chunks to handle large file
chunk_size = 10000
first_chunk = True

for chunk in pd.read_csv(csv_file, chunksize=chunk_size, low_memory=False):
    if first_chunk:
        chunk.to_sql('service_requests', engine, if_exists='replace', index=False)
        print(f"Created table 'service_requests' with {len(chunk)} rows")
        first_chunk = False
    else:
        chunk.to_sql('service_requests', engine, if_exists='append', index=False)
        print(f"Added {len(chunk)} rows")

# Get total count
conn = sqlite3.connect(db_file)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM service_requests")
total = cursor.fetchone()[0]
print(f"\nDatabase created successfully!")
print(f"Total rows: {total}")
print(f"Location: {db_file}")

# Show schema
cursor.execute("PRAGMA table_info(service_requests)")
columns = cursor.fetchall()
print(f"\nTable schema:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")

conn.close()

