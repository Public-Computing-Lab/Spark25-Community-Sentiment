#!/usr/bin/env python3
"""
Download 911 data from Boston's open data portal
"""

import requests
import pandas as pd
import json
import os
from datetime import datetime
import time

def get_boston_911_data(limit=5000, offset=0):
    """
    Download 911 data from Boston's open data portal
    """
    print("🔍 Fetching 911 data from Boston Open Data Portal...")
    
    # Use the crime incident reports dataset
    # This is the main crime data from Boston
    resource_id = "12cb3883-56f5-47de-afa5-3b1cf61bb257"
    base_url = "https://data.boston.gov/api/3/action/datastore_search"
    
    all_records = []
    total_fetched = 0
    
    while True:
        params = {
            'resource_id': resource_id,
            'limit': limit,
            'offset': offset
        }
        
        try:
            print(f"📥 Fetching records {offset} to {offset + limit}...")
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not data['success']:
                print(f"❌ API Error: {data['error']}")
                break
                
            records = data['result']['records']
            if not records:
                print("✅ No more records to fetch")
                break
                
            all_records.extend(records)
            total_fetched += len(records)
            
            print(f"✅ Fetched {len(records)} records (Total: {total_fetched})")
            
            # Check if we got less than the limit (end of data)
            if len(records) < limit:
                print("✅ Reached end of data")
                break
                
            offset += limit
            
            # Be nice to the API
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            break
    
    if all_records:
        print(f"📊 Total records fetched: {len(all_records)}")
        
        # Convert to DataFrame
        df = pd.DataFrame(all_records)
        
        # Save to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"boston_911_data_{timestamp}.csv"
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        df.to_csv(filepath, index=False)
        print(f"💾 Data saved to: {filepath}")
        
        # Print data info
        print(f"📈 Data shape: {df.shape}")
        print(f"📅 Date range: {df['OCCURRED_ON_DATE'].min()} to {df['OCCURRED_ON_DATE'].max()}")
        print(f"🏘️ Districts: {df['DISTRICT'].unique()}")
        
        return df, filepath
    else:
        print("❌ No data fetched")
        return None, None

def get_911_shots_fired_data():
    """
    Get specifically shots fired incidents
    """
    print("🔍 Fetching shots fired data...")
    
    # Get all crime data first
    df, filepath = get_boston_911_data()
    
    if df is not None:
        # Filter for shots fired incidents
        shots_fired = df[df['OFFENSE_CODE_GROUP'].str.contains('SHOTS', case=False, na=False)]
        
        if not shots_fired.empty:
            shots_filename = filepath.replace('.csv', '_shots_fired.csv')
            shots_fired.to_csv(shots_filename, index=False)
            print(f"🔫 Shots fired data saved to: {shots_filename}")
            return shots_fired, shots_filename
        else:
            print("❌ No shots fired incidents found")
            return None, None
    
    return None, None

if __name__ == "__main__":
    print("🚨 Boston 911 Data Downloader")
    print("=" * 40)
    
    # Download all 911 data
    df_all, filepath_all = get_boston_911_data()
    
    if df_all is not None:
        print("\n" + "=" * 40)
        print("🔫 Downloading shots fired data specifically...")
        df_shots, filepath_shots = get_911_shots_fired_data()
        
        print("\n✅ Download complete!")
        print(f"📁 All data: {filepath_all}")
        if filepath_shots:
            print(f"🔫 Shots fired: {filepath_shots}")
    else:
        print("❌ Download failed")
