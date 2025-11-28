#!/usr/bin/env python3
"""
Test script to check if the CKAN API returns records in chronological order.
This helps determine if we can optimize incremental syncs by only fetching the first N records.
"""

import sys
import requests
import pandas as pd
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL

# Boston CKAN API base URL
BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"

def test_record_ordering(resource_id: str, date_field: str, limit: int = 20000):
    """
    Fetch the first N records and check their date ordering.
    
    Args:
        resource_id: CKAN resource ID
        date_field: Name of the date field to check
        limit: Number of records to fetch
    """
    print(f"Testing record ordering for resource: {resource_id}")
    print(f"Fetching first {limit} records...")
    print("=" * 60)
    
    url = f"{BOSTON_CKAN_API}/datastore_search"
    params = {
        'resource_id': resource_id,
        'limit': limit,
        'offset': 0
    }
    
    try:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('success'):
            error_msg = data.get('error', {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get('message', str(error_msg))
            raise Exception(f"API Error: {error_msg}")
        
        records = data['result']['records']
        total_available = data['result'].get('total', len(records))
        
        print(f"[OK] Fetched {len(records)} records (Total available: {total_available})")
        
        if not records:
            print("[WARNING] No records returned")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(records)
        
        # Normalize date field name
        date_col = date_field.replace(' ', '_').replace('-', '_').lower()
        
        # Try to find the date column (case-insensitive)
        date_col_found = None
        for col in df.columns:
            if col.lower() == date_col.lower():
                date_col_found = col
                break
        
        if not date_col_found:
            print(f"[WARNING] Date field '{date_field}' not found in records")
            print(f"   Available columns: {', '.join(df.columns[:10])}")
            return
        
        print(f"\n[INFO] Analyzing date field: '{date_col_found}'")
        
        # Convert to datetime
        df[date_col_found] = pd.to_datetime(df[date_col_found], errors='coerce')
        
        # Handle timezone-aware columns
        dtype_str = str(df[date_col_found].dtype)
        if 'UTC' in dtype_str or '[ns, UTC]' in dtype_str:
            df[date_col_found] = pd.to_datetime(df[date_col_found].astype(str), errors='coerce')
        
        # Remove null dates
        df_valid = df[df[date_col_found].notna()].copy()
        
        if len(df_valid) == 0:
            print("[WARNING] No valid dates found")
            return
        
        # Sort by date to check ordering
        df_sorted = df_valid.sort_values(date_col_found)
        
        # Get first and last records (by position, not date)
        first_record_date = df_valid.iloc[0][date_col_found]
        last_record_date = df_valid.iloc[-1][date_col_found]
        
        # Get earliest and latest dates
        earliest_date = df_sorted.iloc[0][date_col_found]
        latest_date = df_sorted.iloc[-1][date_col_found]
        
        print(f"\n[ANALYSIS] Date Analysis:")
        print(f"   First record (position 0): {first_record_date}")
        print(f"   Last record (position {len(df_valid)-1}): {last_record_date}")
        print(f"   Earliest date in dataset: {earliest_date}")
        print(f"   Latest date in dataset: {latest_date}")
        
        # Determine ordering
        print(f"\n[ORDERING] Analysis:")
        if first_record_date >= last_record_date:
            print("   [OK] Records appear to be in DESCENDING order (newest first)")
            print("   [TIP] We can optimize by fetching only the first N records for incremental syncs!")
        elif first_record_date <= last_record_date:
            print("   [OK] Records appear to be in ASCENDING order (oldest first)")
            print("   [WARNING] We need to fetch all records or use offset to get latest records")
        else:
            print("   [WARNING] Records appear to be in RANDOM order")
            print("   [WARNING] We need to fetch all records and filter")
        
        # Check if latest date is in first 100 records
        latest_in_first_100 = df_valid.head(100)[date_col_found].max()
        print(f"\n[CHECK] Latest date in first 100 records: {latest_in_first_100}")
        if latest_in_first_100 == latest_date:
            print("   [OK] Latest records are at the beginning - we can optimize!")
        else:
            print("   [WARNING] Latest records are not at the beginning")
        
        # Show date distribution
        print(f"\n[DISTRIBUTION] Date Distribution (first 10 vs last 10):")
        print(f"   First 10 dates: {df_valid.head(10)[date_col_found].tolist()}")
        print(f"   Last 10 dates: {df_valid.tail(10)[date_col_found].tolist()}")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test CKAN API record ordering')
    parser.add_argument('--resource-id', type=str, required=True, help='CKAN resource ID')
    parser.add_argument('--date-field', type=str, required=True, help='Date field name')
    parser.add_argument('--limit', type=int, default=20000, help='Number of records to fetch')
    
    args = parser.parse_args()
    
    test_record_ordering(args.resource_id, args.date_field, args.limit)

