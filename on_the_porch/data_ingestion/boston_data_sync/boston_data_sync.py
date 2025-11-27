#!/usr/bin/env python3
"""
Automated sync script for Boston Open Data Portal (data.boston.gov) to MySQL.

This script:
- Fetches data from Boston's CKAN API
- Syncs data to MySQL with incremental updates
- Handles multiple datasets
- Can be scheduled to run automatically
"""

import os
import sys
import json
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import pymysql
from pymysql.cursors import DictCursor

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

# Boston CKAN API base URL
BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"

# Default MySQL connection settings (can be overridden by environment variables)
MYSQL_CONFIG = {
    'host': os.getenv("MYSQL_HOST", "127.0.0.1"),
    'port': int(os.getenv("MYSQL_PORT", "3306")),
    'user': os.getenv("MYSQL_USER", "root"),
    'password': os.getenv("MYSQL_PASSWORD", ""),
    'database': os.getenv("MYSQL_DB", "rethink_ai_boston"),
    'charset': 'utf8mb4',
}


class BostonDataSyncer:
    """Sync data from Boston Open Data Portal to MySQL."""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize the syncer.
        
        Args:
            config_file: Path to JSON config file with dataset definitions.
                        If None, uses default location.
        """
        if config_file is None:
            config_file = Path(__file__).parent / "boston_datasets_config.json"
        
        self.config_file = Path(config_file)
        self.datasets_config = self._load_config()
        self.mysql_conn = None
        
    def _load_config(self) -> Dict:
        """Load dataset configuration from JSON file."""
        if not self.config_file.exists():
            print(f"⚠️  Config file not found: {self.config_file}")
            print("   Creating default config file...")
            self._create_default_config()
        
        with open(self.config_file, 'r') as f:
            return json.load(f)
    
    def _create_default_config(self):
        """Create a default configuration file with example datasets."""
        default_config = {
            "datasets": [
                {
                    "name": "crime_incident_reports",
                    "resource_id": "b973d8cb-eeb2-4e7e-99da-c92938efc9c0",
                    "table_name": "crime_incident_reports",
                    "primary_key": "INCIDENT_NUMBER",
                    "date_field": "OCCURRED_ON_DATE",
                    "description": "Crime incident reports from Boston Police Department",
                    "enabled": True
                },
                {
                    "name": "311_service_requests",
                    "resource_id": "dff4d804-5031-443a-8409-8344efd0e5c8",
                    "table_name": "service_requests_311",
                    "primary_key": "case_enquiry_id",
                    "date_field": "open_dt",
                    "description": "311 service requests (2024)",
                    "enabled": False
                }
            ],
            "sync_settings": {
                "batch_size": 20000,
                "max_records_per_sync": 100000,
                "rate_limit_delay": 1.0,
                "incremental_sync": True,
                "days_to_sync": 30
            }
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        print(f"✅ Created default config: {self.config_file}")
        print("   Please edit this file to configure your datasets.")
    
    def _get_mysql_connection(self):
        """Get MySQL connection, reusing existing if available."""
        if self.mysql_conn is None or not self.mysql_conn.open:
            try:
                self.mysql_conn = pymysql.connect(
                    **MYSQL_CONFIG,
                    cursorclass=DictCursor,
                    autocommit=False
                )
                print(f"✅ Connected to MySQL: {MYSQL_CONFIG['database']}")
            except Exception as e:
                print(f"❌ MySQL connection failed: {e}")
                raise
        return self.mysql_conn
    
    def _close_mysql_connection(self):
        """Close MySQL connection."""
        if self.mysql_conn and self.mysql_conn.open:
            self.mysql_conn.close()
            self.mysql_conn = None
    
    def fetch_dataset(self, resource_id: str, limit: int = 20000, offset: int = 0, 
                     filters: Optional[Dict] = None, date_field: Optional[str] = None,
                     date_from: Optional[str] = None, date_to: Optional[str] = None) -> List[Dict]:
        """
        Fetch data from Boston CKAN API.
        
        Args:
            resource_id: CKAN resource ID
            limit: Number of records per request
            offset: Starting offset
            filters: Optional filters (e.g., exact match)
            date_field: Field name for date filtering
            date_from: Start date for range filter (YYYY-MM-DD)
            date_to: End date for range filter (YYYY-MM-DD)
        
        Returns:
            List of records
        """
        url = f"{BOSTON_CKAN_API}/datastore_search"
        params = {
            'resource_id': resource_id,
            'limit': limit,
            'offset': offset
        }
        
        # Add exact match filters if provided
        if filters:
            # CKAN filters use format: {"field": "value"} for exact matches
            params['filters'] = json.dumps(filters)
        
        # CKAN datastore_search doesn't support date range filters directly
        # We'll fetch all data and filter in pandas, or use filters for exact matches only
        # For date ranges, we need to fetch and filter client-side
        # Note: This is less efficient but necessary due to CKAN API limitations
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('success'):
                error_msg = data.get('error', {})
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get('message', str(error_msg))
                raise Exception(f"API Error: {error_msg}")
            
            return data['result']['records']
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            raise
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            raise
    
    def fetch_all_records(self, resource_id: str, max_records: Optional[int] = None,
                         filters: Optional[Dict] = None, batch_size: int = 20000,
                         date_field: Optional[str] = None, date_from: Optional[str] = None,
                         date_to: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch all records from a dataset.
        
        Args:
            resource_id: CKAN resource ID
            max_records: Maximum number of records to fetch (None = all)
            filters: Optional exact match filters
            batch_size: Records per API call
            date_field: Field name for date range filtering
            date_from: Start date for range filter (YYYY-MM-DD)
            date_to: End date for range filter (YYYY-MM-DD)
        
        Returns:
            DataFrame with all records
        """
        print(f"📥 Fetching all records from resource {resource_id}...")
        if date_from or date_to:
            print(f"   📅 Date range: {date_from or 'start'} to {date_to or 'end'}")
        
        all_records = []
        offset = 0
        total_fetched = 0
        
        while True:
            if max_records and total_fetched >= max_records:
                break
            
            current_limit = min(batch_size, max_records - total_fetched) if max_records else batch_size
            
            try:
                records = self.fetch_dataset(resource_id, limit=current_limit, 
                                            offset=offset, filters=filters,
                                            date_field=date_field, date_from=date_from, date_to=date_to)
                
                if not records:
                    break
                
                all_records.extend(records)
                total_fetched += len(records)
                
                print(f"   Fetched {len(records)} records (Total: {total_fetched})")
                
                if len(records) < current_limit:
                    break
                
                offset += len(records)
                
                # Rate limiting
                time.sleep(self.datasets_config['sync_settings']['rate_limit_delay'])
            
            except Exception as e:
                print(f"❌ Error during fetch: {e}")
                break
        
        if not all_records:
            print("⚠️  No records fetched")
            return pd.DataFrame()
        
        df = pd.DataFrame(all_records)
        
        # Apply date range filtering client-side if needed
        if date_field and (date_from or date_to) and len(df) > 0:
            # Normalize date_field name
            date_col = date_field.replace(' ', '_').replace('-', '_').lower()
            if date_col in df.columns:
                # Convert to datetime
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                
                # Handle timezone-aware columns: convert to timezone-naive for comparison
                if pd.api.types.is_datetime64_any_dtype(df[date_col]):
                    # Check if the column is timezone-aware and strip it
                    if df[date_col].dt.tz is not None:
                        df[date_col] = df[date_col].dt.tz_localize(None)
                
                # Filter by date range (ensure both sides are timezone-naive)
                original_count = len(df)
                if date_from:
                    date_from_dt = pd.to_datetime(date_from)
                    if isinstance(date_from_dt, pd.Timestamp) and hasattr(date_from_dt, 'tz') and date_from_dt.tz is not None:
                        date_from_dt = date_from_dt.tz_localize(None)
                    df = df[df[date_col] >= date_from_dt]
                if date_to:
                    date_to_dt = pd.to_datetime(date_to)
                    if isinstance(date_to_dt, pd.Timestamp) and hasattr(date_to_dt, 'tz') and date_to_dt.tz is not None:
                        date_to_dt = date_to_dt.tz_localize(None)
                    df = df[df[date_col] <= date_to_dt]
                
                filtered_count = len(df)
                if original_count != filtered_count:
                    print(f"   📅 Filtered to {filtered_count:,} records (from {original_count:,})")
        
        print(f"✅ Total records fetched: {len(df)}")
        return df
    
    def get_table_schema(self, df: pd.DataFrame, table_name: str, 
                        primary_key: str) -> str:
        """
        Generate MySQL CREATE TABLE statement from DataFrame.
        
        Args:
            df: DataFrame with data
            table_name: Name of the table
            primary_key: Column name to use as primary key
        
        Returns:
            SQL CREATE TABLE statement
        """
        columns = []
        
        for col in df.columns:
            col_clean = col.replace(' ', '_').replace('-', '_').lower()
            dtype = df[col].dtype
            
            if col_clean == primary_key.lower().replace(' ', '_').replace('-', '_'):
                col_def = f"`{col_clean}` VARCHAR(255) PRIMARY KEY"
            elif pd.api.types.is_integer_dtype(dtype):
                col_def = f"`{col_clean}` BIGINT"
            elif pd.api.types.is_float_dtype(dtype):
                col_def = f"`{col_clean}` DECIMAL(15, 8)"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                col_def = f"`{col_clean}` DATETIME"
            elif pd.api.types.is_bool_dtype(dtype):
                col_def = f"`{col_clean}` BOOLEAN"
            else:
                # String type - estimate length
                max_len = df[col].astype(str).str.len().max()
                varchar_len = min(max(max_len * 2, 255), 65535)  # Reasonable max
                col_def = f"`{col_clean}` VARCHAR({varchar_len})"
            
            columns.append(col_def)
        
        # Add indexes on common fields
        indexes = []
        date_fields = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
        for date_field in date_fields[:2]:  # Limit to 2 date indexes
            col_clean = date_field.replace(' ', '_').replace('-', '_').lower()
            indexes.append(f"INDEX idx_{col_clean} (`{col_clean}`)")
        
        index_sql = ",\n    ".join(indexes) if indexes else ""
        if index_sql:
            index_sql = ",\n    " + index_sql
        
        # Build columns string separately to avoid f-string backslash issue
        columns_str = ",\n    ".join(columns)
        
        sql = f"""CREATE TABLE IF NOT EXISTS `{table_name}` (
    {columns_str}{index_sql}
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"""
        
        return sql
    
    def sync_dataset(self, dataset_config: Dict, incremental: bool = True) -> Dict:
        """
        Sync a single dataset to MySQL.
        
        Args:
            dataset_config: Dataset configuration dict
            incremental: Whether to do incremental sync (only new/updated records)
        
        Returns:
            Dict with sync statistics
        """
        name = dataset_config['name']
        resource_id = dataset_config['resource_id']
        table_name = dataset_config['table_name']
        primary_key = dataset_config.get('primary_key')
        date_field = dataset_config.get('date_field')
        
        # Skip placeholder resources
        if resource_id.startswith('PLACEHOLDER'):
            print(f"\n⏭️  Skipping {name}: Resource ID not yet available")
            return {'dataset': name, 'records_fetched': 0, 'records_inserted': 0, 
                   'records_updated': 0, 'errors': []}
        
        print(f"\n{'='*60}")
        print(f"🔄 Syncing dataset: {name}")
        print(f"   Table: {table_name}")
        print(f"   Resource ID: {resource_id}")
        print(f"{'='*60}")
        
        stats = {
            'dataset': name,
            'records_fetched': 0,
            'records_inserted': 0,
            'records_updated': 0,
            'errors': []
        }
        
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            
            # Determine if we need incremental sync (only fetch new data)
            filters = None
            date_from = None
            date_to = datetime.now().strftime('%Y-%m-%d')  # Today
            date_field_normalized = date_field.replace(' ', '_').replace('-', '_').lower() if date_field else None
            
            # Check if table exists and has data - if so, do incremental sync
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists and date_field_normalized:
                try:
                    # Get the latest date from the database
                    cursor.execute(f"SELECT MAX(`{date_field_normalized}`) as max_date FROM `{table_name}`")
                    result = cursor.fetchone()
                    if result and result.get('max_date'):
                        max_date = result['max_date']
                        if isinstance(max_date, str):
                            max_date = pd.to_datetime(max_date)
                        elif hasattr(max_date, 'date'):
                            max_date = pd.to_datetime(max_date)
                        # Only fetch records newer than the latest date we have
                        # Add a small buffer (1 day) to catch any updates to existing records
                        sync_from = pd.to_datetime(max_date) - timedelta(days=1)
                        date_from = sync_from.strftime('%Y-%m-%d')
                        print(f"   📅 Incremental sync: fetching records from {date_from} to {date_to}")
                    else:
                        print(f"   📅 Table exists but empty - doing full sync from today back to earliest date")
                except Exception as e:
                    print(f"   ⚠️  Could not determine last sync date: {e}")
                    print(f"   📥 Doing full sync...")
            else:
                print(f"   📅 Full sync: fetching all records from today ({date_to}) back to earliest available date")
            
            # Fetch data (no max_records limit for full historical sync)
            max_records = self.datasets_config['sync_settings'].get('max_records_per_sync')
            # If max_records is None or 0, fetch all records
            if max_records is None or max_records == 0:
                max_records = None
            
            df = self.fetch_all_records(resource_id, max_records=max_records, filters=filters,
                                       date_field=date_field_normalized, date_from=date_from, date_to=date_to)
            
            # Note: Date filtering is already done in fetch_all_records, so we just need to ensure
            # the data is ready for database insertion (timezone-naive)
            if date_field_normalized and len(df) > 0 and date_field_normalized in df.columns:
                # Convert to datetime if not already
                if not pd.api.types.is_datetime64_any_dtype(df[date_field_normalized]):
                    df[date_field_normalized] = pd.to_datetime(df[date_field_normalized], errors='coerce')
                
                # Handle timezone-aware columns: convert datetime64[ns, UTC] to timezone-naive
                # This is critical for MySQL compatibility and to avoid comparison errors
                if pd.api.types.is_datetime64_any_dtype(df[date_field_normalized]):
                    # Check if the column is timezone-aware and strip it
                    if df[date_field_normalized].dt.tz is not None:
                        df[date_field_normalized] = df[date_field_normalized].dt.tz_localize(None)
            
            if df.empty:
                print("   ⚠️  No data to sync")
                return stats
            
            stats['records_fetched'] = len(df)
            
            # Normalize column names (MySQL-friendly)
            df.columns = [col.replace(' ', '_').replace('-', '_').lower() for col in df.columns]
            
            # Create table if it doesn't exist
            if primary_key:
                pk_col = primary_key.replace(' ', '_').replace('-', '_').lower()
            else:
                pk_col = df.columns[0]  # Use first column as PK
            
            # Check if table exists (already checked above, but keep for compatibility)
            if not table_exists:
                cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                print(f"   📋 Creating table: {table_name}")
                create_sql = self.get_table_schema(df, table_name, pk_col)
                cursor.execute(create_sql)
                conn.commit()
            else:
                # Check if primary key column exists
                cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE '{pk_col}'")
                if not cursor.fetchone():
                    print(f"   ⚠️  Primary key column '{pk_col}' not found in existing table")
                    # Add it if possible
                    try:
                        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{pk_col}` VARCHAR(255) PRIMARY KEY FIRST")
                        conn.commit()
                    except Exception as e:
                        print(f"   ❌ Could not add primary key: {e}")
            
            # Prepare data for insertion
            # Convert date columns and strip timezone if present
            for col in df.columns:
                if 'date' in col.lower() or 'time' in col.lower():
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                    # Strip timezone if present (MySQL doesn't support timezone-aware datetimes)
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        if df[col].dt.tz is not None:
                            df[col] = df[col].dt.tz_localize(None)
            
            # Build INSERT ... ON DUPLICATE KEY UPDATE statement
            columns = list(df.columns)
            placeholders = ', '.join(['%s'] * len(columns))
            col_names = ', '.join([f"`{col}`" for col in columns])
            
            update_clause = ', '.join([f"`{col}` = VALUES(`{col}`)" for col in columns if col != pk_col])
            
            insert_sql = f"""
            INSERT INTO `{table_name}` ({col_names})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_clause}
            """
            
            # Insert data in batches
            batch_size = self.datasets_config['sync_settings']['batch_size']
            total_inserted = 0
            total_updated = 0
            
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i:i+batch_size]
                
                # Convert DataFrame to list of tuples, handling NaN values
                records = []
                for _, row in batch.iterrows():
                    record = tuple(
                        None if pd.isna(val) else val
                        for val in row.values
                    )
                    records.append(record)
                
                try:
                    # Try to check which records are new vs updates (for stats only)
                    try:
                        if pk_col in columns:
                            pk_idx = columns.index(pk_col)
                            pk_values = [r[pk_idx] for r in records if r[pk_idx] is not None]
                            if pk_values:
                                placeholders_pk = ', '.join(['%s'] * len(pk_values))
                                cursor.execute(
                                    f"SELECT `{pk_col}` FROM `{table_name}` WHERE `{pk_col}` IN ({placeholders_pk})",
                                    pk_values
                                )
                                existing_pks = {row[pk_col] for row in cursor.fetchall()}
                                new_count = sum(1 for pk in pk_values if pk not in existing_pks)
                                total_updated += len(records) - new_count
                                total_inserted += new_count
                            else:
                                total_inserted += len(records)
                        else:
                            total_inserted += len(records)
                    except Exception:
                        # If we can't determine, assume all are inserts
                        total_inserted += len(records)
                    
                    cursor.executemany(insert_sql, records)
                    conn.commit()
                    
                    print(f"   ✅ Inserted batch {i//batch_size + 1}/{(len(df)-1)//batch_size + 1} "
                          f"({len(records)} records)")
                
                except Exception as e:
                    conn.rollback()
                    error_msg = f"Error inserting batch {i//batch_size + 1}: {e}"
                    print(f"   ❌ {error_msg}")
                    stats['errors'].append(error_msg)
            
            stats['records_inserted'] = total_inserted
            stats['records_updated'] = total_updated
            
            print(f"\n   ✅ Sync complete!")
            print(f"      Fetched: {stats['records_fetched']}")
            print(f"      Inserted: {stats['records_inserted']}")
            print(f"      Updated: {stats['records_updated']}")
        
        except Exception as e:
            error_msg = f"Error syncing dataset {name}: {e}"
            print(f"   ❌ {error_msg}")
            stats['errors'].append(error_msg)
        
        return stats
    
    def _get_table_columns(self, cursor, table_name: str) -> set:
        """Get all column names from a table."""
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        rows = cursor.fetchall()
        # Handle both DictCursor (returns dicts) and regular cursor (returns tuples)
        if rows and isinstance(rows[0], dict):
            # DictCursor returns dictionaries with 'Field' key
            return {row.get('Field', '').lower() for row in rows if row.get('Field')}
        else:
            # Regular cursor returns tuples, first element is column name
            return {row[0].lower() for row in rows if row}
    
    def create_filtered_tables_from_crime_data(self):
        """
        Create shots_fired_data and homicide_data tables by filtering crime_incident_reports.
        This should be called after syncing crime_incident_reports.
        """
        conn = None
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            
            # Check if crime_incident_reports table exists
            cursor.execute("SHOW TABLES LIKE 'crime_incident_reports'")
            if not cursor.fetchone():
                print("   ⚠️  crime_incident_reports table not found - skipping filtered tables")
                return
            
            # Get actual column names from the table
            columns = self._get_table_columns(cursor, 'crime_incident_reports')
            print(f"   📋 Found {len(columns)} columns in crime_incident_reports")
            
            # Check which columns we need exist
            has_offense_code_group = 'offense_code_group' in columns
            has_offense_description = 'offense_description' in columns
            has_shooting = 'shooting' in columns
            has_neighborhood = 'neighborhood' in columns
            has_street = 'street' in columns
            has_district = 'district' in columns
            has_year = 'year' in columns
            has_lat = 'lat' in columns
            has_long = 'long' in columns or '`long`' in columns
            has_hour = 'hour' in columns
            has_day_of_week = 'day_of_week' in columns
            has_month = 'month' in columns
            has_incident_number = 'incident_number' in columns
            
            # Print missing columns
            missing_cols = []
            if not has_offense_code_group:
                missing_cols.append("offense_code_group")
            if not has_offense_description:
                missing_cols.append("offense_description")
            if not has_neighborhood:
                missing_cols.append("neighborhood")
            if not has_street:
                missing_cols.append("street")
            if not has_district:
                missing_cols.append("district")
            if not has_year:
                missing_cols.append("year")
            if not has_lat:
                missing_cols.append("lat")
            if not has_long:
                missing_cols.append("long")
            if not has_hour:
                missing_cols.append("hour")
            if not has_day_of_week:
                missing_cols.append("day_of_week")
            if not has_month:
                missing_cols.append("month")
            if not has_incident_number:
                missing_cols.append("incident_number")
            
            if missing_cols:
                print(f"   ⚠️  Missing columns (will use NULL/derived values): {', '.join(missing_cols)}")
            
            if not has_shooting:
                print("   ⚠️  'shooting' column not found - cannot create shots_fired_data")
                return
            
            print("\n   🔫 Creating/updating shots_fired_data table...")
            
            # Create shots_fired_data table matching metadata schema
            # Based on on_the_porch/new_metadata/shots_fired_data.json
            table_columns = [
                "id INT AUTO_INCREMENT PRIMARY KEY",
                "object_id INT",
                "incident_num VARCHAR(20)",
                "incident_date BIGINT",
                "incident_date_time DATETIME",
                "address VARCHAR(255)",
                "district VARCHAR(10)",
                "ballistics_evidence INT DEFAULT 0",
                "latitude DECIMAL(10,8)",
                "longitude DECIMAL(10,8)",
                "census_block_geo_id BIGINT",
                "hour_of_day INT",
                "day_of_week INT",
                "year INT",
                "quarter INT",
                "month INT",
                "neighborhood VARCHAR(20)",
                "geometry_x DECIMAL(10,8)",
                "geometry_y DECIMAL(10,8)",
                "coordinates POINT NULL"
            ]
            
            shots_fired_sql = f"""
            CREATE TABLE IF NOT EXISTS shots_fired_data (
                {', '.join(table_columns)},
                UNIQUE KEY uk_incident_num (incident_num),
                INDEX idx_date (incident_date_time),
                INDEX idx_district (district),
                INDEX idx_coords (latitude, longitude)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
            cursor.execute(shots_fired_sql)
            
            # Check if coordinates column exists, add it if not
            cursor.execute("""
                SELECT COUNT(*) as col_count
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'shots_fired_data' 
                AND COLUMN_NAME = 'coordinates'
            """)
            result = cursor.fetchone()
            has_coordinates = result and result.get('col_count', 0) > 0
            
            if not has_coordinates:
                try:
                    cursor.execute("ALTER TABLE shots_fired_data ADD COLUMN coordinates POINT NULL")
                    conn.commit()
                    print("   ✅ Added coordinates column to shots_fired_data table")
                except Exception as e:
                    print(f"   ⚠️  Could not add coordinates column: {e}")
            else:
                # Check if column is NOT NULL and alter it to allow NULL
                cursor.execute("""
                    SELECT IS_NULLABLE
                    FROM information_schema.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'shots_fired_data' 
                    AND COLUMN_NAME = 'coordinates'
                """)
                result = cursor.fetchone()
                if result and result.get('IS_NULLABLE', '').upper() == 'NO':
                    # Check for spatial indexes on coordinates column that need to be dropped first
                    cursor.execute("""
                        SELECT INDEX_NAME
                        FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'shots_fired_data'
                        AND COLUMN_NAME = 'coordinates'
                        AND INDEX_TYPE = 'SPATIAL'
                    """)
                    spatial_indexes = cursor.fetchall()
                    
                    # Drop any spatial indexes on coordinates
                    for idx in spatial_indexes:
                        idx_name = idx.get('INDEX_NAME') if isinstance(idx, dict) else idx[0]
                        try:
                            cursor.execute(f"ALTER TABLE shots_fired_data DROP INDEX `{idx_name}`")
                            print(f"   ✅ Dropped spatial index {idx_name} on coordinates column")
                        except Exception as e:
                            print(f"   ⚠️  Could not drop spatial index {idx_name}: {e}")
                    
                    # Now modify the column to allow NULL
                    try:
                        cursor.execute("ALTER TABLE shots_fired_data MODIFY COLUMN coordinates POINT NULL")
                        conn.commit()
                        print("   ✅ Modified coordinates column to allow NULL")
                    except Exception as e:
                        print(f"   ⚠️  Could not modify coordinates column: {e}")
                        # If modification fails, drop and recreate the table
                        print("   🔄 Attempting to drop and recreate table...")
                        try:
                            cursor.execute("DROP TABLE IF EXISTS shots_fired_data")
                            cursor.execute(shots_fired_sql)
                            conn.commit()
                            print("   ✅ Recreated shots_fired_data table with correct schema")
                        except Exception as recreate_error:
                            print(f"   ❌ Could not recreate table: {recreate_error}")
            
            # Build SELECT statement matching metadata schema
            # Map from crime_incident_reports to shots_fired_data schema
            select_parts = []
            null_fields = []
            
            # object_id - not available
            select_parts.append("NULL as object_id")
            null_fields.append("object_id")
            
            # incident_num
            if has_incident_number:
                select_parts.append("COALESCE(`incident_number`, '') as incident_num")
            else:
                select_parts.append("COALESCE(`incident_num`, '') as incident_num")
            
            # incident_date (bigint timestamp)
            select_parts.append("UNIX_TIMESTAMP(`occurred_on_date`) as incident_date")
            
            # incident_date_time
            select_parts.append("`occurred_on_date` as incident_date_time")
            
            # address (use street if available)
            if has_street:
                select_parts.append("COALESCE(`street`, '') as address")
            else:
                select_parts.append("'' as address")
            
            # district
            if has_district:
                select_parts.append("COALESCE(`district`, '') as district")
            else:
                select_parts.append("'' as district")
            
            # ballistics_evidence
            if has_offense_description:
                select_parts.append("""CASE 
                    WHEN LOWER(`offense_description`) LIKE '%confirmed%' 
                         OR LOWER(`offense_description`) LIKE '%ballistics%' THEN 1 
                    ELSE 0 
                END as ballistics_evidence""")
            else:
                select_parts.append("0 as ballistics_evidence")
            
            # latitude
            if has_lat:
                select_parts.append("`lat` as latitude")
            else:
                select_parts.append("NULL as latitude")
                null_fields.append("latitude")
            
            # longitude
            if has_long:
                select_parts.append("`long` as longitude")
            else:
                select_parts.append("NULL as longitude")
                null_fields.append("longitude")
            
            # census_block_geo_id - not available
            select_parts.append("NULL as census_block_geo_id")
            null_fields.append("census_block_geo_id")
            
            # hour_of_day - always derive from date to ensure numeric value
            # Don't use the column directly as it may have inconsistent format
            select_parts.append("HOUR(`occurred_on_date`) as hour_of_day")
            
            # day_of_week - always derive from date to ensure numeric value (1=Sunday, 7=Saturday)
            # Don't use the column directly as it may contain text values like "Friday"
            select_parts.append("DAYOFWEEK(`occurred_on_date`) as day_of_week")
            
            # year - always derive from date to ensure consistency
            select_parts.append("YEAR(`occurred_on_date`) as year")
            
            # quarter - always derive from date
            select_parts.append("QUARTER(`occurred_on_date`) as quarter")
            
            # month - always derive from date to ensure numeric value
            select_parts.append("MONTH(`occurred_on_date`) as month")
            
            # neighborhood
            if has_neighborhood:
                select_parts.append("COALESCE(`neighborhood`, '') as neighborhood")
            else:
                select_parts.append("'' as neighborhood")
            
            # geometry_x (use lat)
            if has_lat:
                select_parts.append("`lat` as geometry_x")
            else:
                select_parts.append("NULL as geometry_x")
                null_fields.append("geometry_x")
            
            # geometry_y (use long)
            if has_long:
                select_parts.append("`long` as geometry_y")
            else:
                select_parts.append("NULL as geometry_y")
                null_fields.append("geometry_y")
            
            # coordinates (POINT from lat/long)
            if has_lat and has_long:
                select_parts.append("POINT(`long`, `lat`) as coordinates")
            else:
                select_parts.append("NULL as coordinates")
                null_fields.append("coordinates")
            
            if null_fields:
                print(f"   ⚠️  Shots fired data - Fields set to NULL: {', '.join(null_fields)}")
            
            insert_columns = [
                "object_id", "incident_num", "incident_date", "incident_date_time", "address",
                "district", "ballistics_evidence", "latitude", "longitude", "census_block_geo_id",
                "hour_of_day", "day_of_week", "year", "quarter", "month", "neighborhood",
                "geometry_x", "geometry_y", "coordinates"
            ]
            
            # Use incident_num as unique key for ON DUPLICATE KEY UPDATE
            update_parts = [
                "incident_date = VALUES(incident_date)",
                "incident_date_time = VALUES(incident_date_time)",
                "address = VALUES(address)",
                "district = VALUES(district)",
                "ballistics_evidence = VALUES(ballistics_evidence)",
                "latitude = VALUES(latitude)",
                "longitude = VALUES(longitude)",
                "hour_of_day = VALUES(hour_of_day)",
                "day_of_week = VALUES(day_of_week)",
                "year = VALUES(year)",
                "quarter = VALUES(quarter)",
                "month = VALUES(month)",
                "neighborhood = VALUES(neighborhood)",
                "geometry_x = VALUES(geometry_x)",
                "geometry_y = VALUES(geometry_y)",
                "coordinates = VALUES(coordinates)"
            ]
            
            insert_shots_sql = f"""
            INSERT INTO shots_fired_data 
            ({', '.join(insert_columns)})
            SELECT {', '.join(select_parts)}
            FROM `crime_incident_reports`
            WHERE `shooting` = 1
            ON DUPLICATE KEY UPDATE
                {', '.join(update_parts)}
            """
            cursor.execute(insert_shots_sql)
            shots_count = cursor.rowcount
            print(f"   ✅ Inserted/updated {shots_count} shots fired records")
            
            if not has_offense_description:
                print("   ⚠️  'offense_description' column not found - cannot create homicide_data")
            else:
                print("\n   💀 Creating/updating homicide_data table...")
                
                # Create homicide_data table matching metadata schema
                # Based on on_the_porch/new_metadata/homicide_data.json
                homicide_table_columns = [
                    "id INT AUTO_INCREMENT PRIMARY KEY",
                    "object_id INT",
                    "reporting_event_number VARCHAR(20)",
                    "ruled_date DATETIME",
                    "homicide_date DATETIME",
                    "district VARCHAR(10)",
                    "victim_age INT",
                    "race VARCHAR(50)",
                    "gender VARCHAR(10)",
                    "weapon VARCHAR(20)",
                    "hour_of_day INT",
                    "day_of_week INT",
                    "year INT",
                    "quarter INT",
                    "month INT",
                    "neighborhood VARCHAR(50)",
                    "ethnicity_nibrs VARCHAR(50)"
                ]
                
                homicide_sql = f"""
                CREATE TABLE IF NOT EXISTS homicide_data (
                    {', '.join(homicide_table_columns)},
                    UNIQUE KEY uk_reporting_event (reporting_event_number),
                    INDEX idx_date (homicide_date),
                    INDEX idx_district (district)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """
                cursor.execute(homicide_sql)
                
                # Build SELECT for homicide matching metadata schema
                homicide_select_parts = []
                homicide_null_fields = []
                
                # object_id - not available
                homicide_select_parts.append("NULL as object_id")
                homicide_null_fields.append("object_id")
                
                # reporting_event_number
                if has_incident_number:
                    homicide_select_parts.append("COALESCE(`incident_number`, '') as reporting_event_number")
                else:
                    homicide_select_parts.append("COALESCE(`incident_num`, '') as reporting_event_number")
                
                # ruled_date - not available
                homicide_select_parts.append("NULL as ruled_date")
                homicide_null_fields.append("ruled_date")
                
                # homicide_date
                homicide_select_parts.append("`occurred_on_date` as homicide_date")
                
                # district
                if has_district:
                    homicide_select_parts.append("COALESCE(`district`, '') as district")
                else:
                    homicide_select_parts.append("'' as district")
                    homicide_null_fields.append("district")
                
                # victim_age, race, gender, weapon - not available
                homicide_select_parts.append("NULL as victim_age")
                homicide_null_fields.append("victim_age")
                homicide_select_parts.append("NULL as race")
                homicide_null_fields.append("race")
                homicide_select_parts.append("NULL as gender")
                homicide_null_fields.append("gender")
                homicide_select_parts.append("NULL as weapon")
                homicide_null_fields.append("weapon")
                
                # hour_of_day - always derive from date
                homicide_select_parts.append("HOUR(`occurred_on_date`) as hour_of_day")
                
                # day_of_week - always derive from date to ensure numeric value
                homicide_select_parts.append("DAYOFWEEK(`occurred_on_date`) as day_of_week")
                
                # year - always derive from date
                homicide_select_parts.append("YEAR(`occurred_on_date`) as year")
                
                # quarter - always derive from date
                homicide_select_parts.append("QUARTER(`occurred_on_date`) as quarter")
                
                # month - always derive from date
                homicide_select_parts.append("MONTH(`occurred_on_date`) as month")
                
                # neighborhood
                if has_neighborhood:
                    homicide_select_parts.append("COALESCE(`neighborhood`, '') as neighborhood")
                else:
                    homicide_select_parts.append("'' as neighborhood")
                
                # ethnicity_nibrs - not available
                homicide_select_parts.append("NULL as ethnicity_nibrs")
                homicide_null_fields.append("ethnicity_nibrs")
                
                if homicide_null_fields:
                    print(f"   ⚠️  Homicide data - Fields set to NULL: {', '.join(homicide_null_fields)}")
                
                homicide_insert_columns = [
                    "object_id", "reporting_event_number", "ruled_date", "homicide_date",
                    "district", "victim_age", "race", "gender", "weapon",
                    "hour_of_day", "day_of_week", "year", "quarter", "month",
                    "neighborhood", "ethnicity_nibrs"
                ]
                
                homicide_update_parts = [
                    "homicide_date = VALUES(homicide_date)",
                    "district = VALUES(district)",
                    "hour_of_day = VALUES(hour_of_day)",
                    "day_of_week = VALUES(day_of_week)",
                    "year = VALUES(year)",
                    "quarter = VALUES(quarter)",
                    "month = VALUES(month)",
                    "neighborhood = VALUES(neighborhood)"
                ]
                
                insert_homicide_sql = f"""
                INSERT INTO homicide_data 
                ({', '.join(homicide_insert_columns)})
                SELECT {', '.join(homicide_select_parts)}
                FROM `crime_incident_reports`
                WHERE LOWER(`offense_description`) LIKE '%homicide%'
                ON DUPLICATE KEY UPDATE
                    {', '.join(homicide_update_parts)}
                """
                cursor.execute(insert_homicide_sql)
                homicide_count = cursor.rowcount
                print(f"   ✅ Inserted/updated {homicide_count} homicide records")
            
            conn.commit()
            print("   ✅ Filtered tables created/updated successfully")
            
        except Exception as e:
            print(f"   ❌ Error creating filtered tables: {e}")
            if conn:
                conn.rollback()
            import traceback
            traceback.print_exc()
    
    def sync_all(self) -> Dict:
        """Sync all enabled datasets."""
        print("="*60)
        print("🚀 Boston Open Data Portal → MySQL Sync")
        print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        all_stats = {
            'start_time': datetime.now().isoformat(),
            'datasets_synced': 0,
            'total_records': 0,
            'datasets': []
        }
        
        incremental = self.datasets_config['sync_settings'].get('incremental_sync', True)
        
        for dataset in self.datasets_config['datasets']:
            if not dataset.get('enabled', True):
                print(f"\n⏭️  Skipping disabled dataset: {dataset['name']}")
                continue
            
            # Skip datasets with placeholder resource IDs
            if dataset.get('resource_id', '').startswith('PLACEHOLDER'):
                print(f"\n⏭️  Skipping {dataset['name']}: Resource ID not yet available")
                if dataset.get('note'):
                    print(f"   ℹ️  {dataset['note']}")
                continue
            
            try:
                stats = self.sync_dataset(dataset, incremental=incremental)
                all_stats['datasets'].append(stats)
                all_stats['datasets_synced'] += 1
                all_stats['total_records'] += stats['records_fetched']
                
                # Note: Filtered table creation disabled - shots_fired and shootings are now synced directly from portal
                # if dataset['name'] == 'crime_incident_reports':
                #     self.create_filtered_tables_from_crime_data()
            except Exception as e:
                print(f"❌ Failed to sync {dataset['name']}: {e}")
                all_stats['datasets'].append({
                    'dataset': dataset['name'],
                    'errors': [str(e)]
                })
        
        all_stats['end_time'] = datetime.now().isoformat()
        duration = datetime.fromisoformat(all_stats['end_time']) - datetime.fromisoformat(all_stats['start_time'])
        all_stats['duration_seconds'] = duration.total_seconds()
        
        # Print summary
        print("\n" + "="*60)
        print("📊 Sync Summary")
        print("="*60)
        print(f"   Datasets synced: {all_stats['datasets_synced']}")
        print(f"   Total records: {all_stats['total_records']}")
        print(f"   Duration: {duration}")
        print("="*60)
        
        # Save sync log
        log_file = Path(__file__).parent / "boston_sync_log.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(all_stats) + '\n')
        
        return all_stats
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connections."""
        self._close_mysql_connection()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync Boston Open Data Portal to MySQL')
    parser.add_argument('--config', type=str, help='Path to config JSON file')
    parser.add_argument('--dataset', type=str, help='Sync only this dataset (by name)')
    parser.add_argument('--full', action='store_true', help='Do full sync (not incremental)')
    parser.add_argument('--list-datasets', action='store_true', help='List configured datasets')
    
    args = parser.parse_args()
    
    with BostonDataSyncer(config_file=args.config) as syncer:
        if args.list_datasets:
            print("📋 Configured Datasets:")
            for dataset in syncer.datasets_config['datasets']:
                status = "✅ Enabled" if dataset.get('enabled', True) else "⏸️  Disabled"
                print(f"   {status}: {dataset['name']} → {dataset['table_name']}")
            return
        
        if args.dataset:
            # Sync single dataset
            dataset = next((d for d in syncer.datasets_config['datasets'] 
                          if d['name'] == args.dataset), None)
            if not dataset:
                print(f"❌ Dataset '{args.dataset}' not found")
                return
            syncer.sync_dataset(dataset, incremental=not args.full)
        else:
            # Sync all enabled datasets
            syncer.sync_all()


if __name__ == "__main__":
    main()

