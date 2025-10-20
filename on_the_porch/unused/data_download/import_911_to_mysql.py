#!/usr/bin/env python3
"""
Import 911 data into MySQL database
"""

import pandas as pd
import mysql.connector
from mysql.connector import Error
import os
from datetime import datetime
import glob
import numpy as np

def connect_to_mysql():
    """Connect to MySQL database"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='rethinkai_user',
            password='MySecureUserPass123!',
            database='rethinkai_db'
        )
        print("✅ Connected to MySQL database")
        return connection
    except Error as e:
        print(f"❌ Error connecting to MySQL: {e}")
        return None

def create_911_tables(connection):
    """Create the required tables for 911 data"""
    cursor = connection.cursor()
    
    try:
        # Create shots_fired_data table
        shots_fired_table = """
        CREATE TABLE IF NOT EXISTS shots_fired_data (
            id VARCHAR(255) PRIMARY KEY,
            incident_date_time DATETIME,
            ballistics_evidence INT DEFAULT 0,
            latitude DECIMAL(10,8),
            longitude DECIMAL(11,8),
            district VARCHAR(10),
            neighborhood VARCHAR(100),
            year INT,
            offense_code_group VARCHAR(255),
            street VARCHAR(255),
            INDEX idx_date (incident_date_time),
            INDEX idx_district (district),
            INDEX idx_coords (latitude, longitude)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        
        # Create homicide_data table
        homicide_table = """
        CREATE TABLE IF NOT EXISTS homicide_data (
            id VARCHAR(255) PRIMARY KEY,
            homicide_date DATETIME,
            district VARCHAR(10),
            neighborhood VARCHAR(100),
            offense_code_group VARCHAR(255),
            street VARCHAR(255),
            INDEX idx_date (homicide_date),
            INDEX idx_district (district)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        
        cursor.execute(shots_fired_table)
        print("✅ Created shots_fired_data table")
        
        cursor.execute(homicide_table)
        print("✅ Created homicide_data table")
        
        connection.commit()
        
    except Error as e:
        print(f"❌ Error creating tables: {e}")
        return False
    
    finally:
        cursor.close()
    
    return True

def process_911_data(df):
    """Process and clean the 911 data"""
    print("🔧 Processing 911 data...")
    
    # Convert date columns
    df['OCCURRED_ON_DATE'] = pd.to_datetime(df['OCCURRED_ON_DATE'], errors='coerce')
    
    # Extract year
    df['year'] = df['OCCURRED_ON_DATE'].dt.year
    
    # Clean coordinates
    df['Lat'] = pd.to_numeric(df['Lat'], errors='coerce')
    df['Long'] = pd.to_numeric(df['Long'], errors='coerce')
    
    # Filter out invalid coordinates
    df = df.dropna(subset=['Lat', 'Long'])
    
    # Create unique ID if not exists
    if 'INCIDENT_NUMBER' not in df.columns:
        df['INCIDENT_NUMBER'] = df.index.astype(str)
    
    print(f"📊 Processed {len(df)} records")
    return df

def import_shots_fired_data(connection, df):
    """Import shots fired data"""
    cursor = connection.cursor()
    
    try:
        # Filter for shooting incidents using the SHOOTING column
        shots_fired = df[df['SHOOTING'] == 1]
        
        if shots_fired.empty:
            print("❌ No shots fired incidents found")
            return False
        
        print(f"🔫 Found {len(shots_fired)} shots fired incidents")
        
        # Prepare data for insertion
        insert_query = """
        INSERT INTO shots_fired_data 
        (id, incident_date_time, ballistics_evidence, latitude, longitude, 
         district, neighborhood, year, offense_code_group, street)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        incident_date_time = VALUES(incident_date_time),
        ballistics_evidence = VALUES(ballistics_evidence),
        latitude = VALUES(latitude),
        longitude = VALUES(longitude),
        district = VALUES(district),
        neighborhood = VALUES(neighborhood),
        year = VALUES(year),
        offense_code_group = VALUES(offense_code_group),
        street = VALUES(street)
        """
        
        records = []
        for _, row in shots_fired.iterrows():
            # Determine if ballistics evidence exists (simplified logic)
            ballistics_evidence = 1 if 'CONFIRMED' in str(row.get('OFFENSE_DESCRIPTION', '')).upper() else 0
            
            # Handle NaN values
            incident_number = str(row.get('INCIDENT_NUMBER', '')) if pd.notna(row.get('INCIDENT_NUMBER')) else ''
            occurred_date = row.get('OCCURRED_ON_DATE') if pd.notna(row.get('OCCURRED_ON_DATE')) else None
            lat = row.get('Lat') if pd.notna(row.get('Lat')) else None
            lng = row.get('Long') if pd.notna(row.get('Long')) else None
            district = str(row.get('DISTRICT', '')) if pd.notna(row.get('DISTRICT')) else ''
            year = row.get('YEAR') if pd.notna(row.get('YEAR')) else None
            offense_desc = str(row.get('OFFENSE_DESCRIPTION', '')) if pd.notna(row.get('OFFENSE_DESCRIPTION')) else ''
            street = str(row.get('STREET', '')) if pd.notna(row.get('STREET')) else ''
            
            record = (
                incident_number,
                occurred_date,
                ballistics_evidence,
                lat,
                lng,
                district,
                '',  # No neighborhood field in this dataset
                year,
                offense_desc,
                street
            )
            records.append(record)
        
        # Insert in batches
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            cursor.executemany(insert_query, batch)
            connection.commit()
            print(f"📥 Inserted batch {i//batch_size + 1}/{(len(records)-1)//batch_size + 1}")
        
        print(f"✅ Successfully imported {len(records)} shots fired records")
        return True
        
    except Error as e:
        print(f"❌ Error importing shots fired data: {e}")
        return False
    
    finally:
        cursor.close()

def import_homicide_data(connection, df):
    """Import homicide data"""
    cursor = connection.cursor()
    
    try:
        # Filter for homicide incidents using OFFENSE_DESCRIPTION
        homicides = df[df['OFFENSE_DESCRIPTION'].str.contains('HOMICIDE', case=False, na=False)]
        
        if homicides.empty:
            print("❌ No homicide incidents found")
            return False
        
        print(f"💀 Found {len(homicides)} homicide incidents")
        
        # Prepare data for insertion
        insert_query = """
        INSERT INTO homicide_data 
        (id, homicide_date, district, neighborhood, offense_code_group, street)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        homicide_date = VALUES(homicide_date),
        district = VALUES(district),
        neighborhood = VALUES(neighborhood),
        offense_code_group = VALUES(offense_code_group),
        street = VALUES(street)
        """
        
        records = []
        for _, row in homicides.iterrows():
            record = (
                str(row.get('INCIDENT_NUMBER', '')),
                row.get('OCCURRED_ON_DATE'),
                row.get('DISTRICT', ''),
                '',  # No neighborhood field in this dataset
                row.get('OFFENSE_DESCRIPTION', ''),
                row.get('STREET', '')
            )
            records.append(record)
        
        # Insert in batches
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            cursor.executemany(insert_query, batch)
            connection.commit()
            print(f"📥 Inserted batch {i//batch_size + 1}/{(len(records)-1)//batch_size + 1}")
        
        print(f"✅ Successfully imported {len(records)} homicide records")
        return True
        
    except Error as e:
        print(f"❌ Error importing homicide data: {e}")
        return False
    
    finally:
        cursor.close()

def find_latest_csv():
    """Find the most recent CSV file"""
    csv_files = glob.glob("boston_crime_data_*.csv")
    if not csv_files:
        print("❌ No CSV files found. Run download_crime_data.py first.")
        return None
    
    latest_file = max(csv_files, key=os.path.getctime)
    print(f"📁 Using latest file: {latest_file}")
    return latest_file

def main():
    """Main function to import 911 data"""
    print("🚨 Boston 911 Data Importer")
    print("=" * 40)
    
    # Find the latest CSV file
    csv_file = find_latest_csv()
    if not csv_file:
        return
    
    # Load data
    print(f"📖 Loading data from {csv_file}...")
    try:
        df = pd.read_csv(csv_file)
        print(f"📊 Loaded {len(df)} records")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return
    
    # Connect to database
    connection = connect_to_mysql()
    if not connection:
        return
    
    try:
        # Create tables
        if not create_911_tables(connection):
            return
        
        # Process data
        df = process_911_data(df)
        
        # Import shots fired data
        print("\n🔫 Importing shots fired data...")
        import_shots_fired_data(connection, df)
        
        # Import homicide data
        print("\n💀 Importing homicide data...")
        import_homicide_data(connection, df)
        
        print("\n✅ Import complete!")
        
        # Show summary
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM shots_fired_data")
        shots_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM homicide_data")
        homicide_count = cursor.fetchone()[0]
        
        print(f"📊 Database summary:")
        print(f"   🔫 Shots fired records: {shots_count}")
        print(f"   💀 Homicide records: {homicide_count}")
        
    except Exception as e:
        print(f"❌ Error during import: {e}")
    
    finally:
        connection.close()

if __name__ == "__main__":
    main()
