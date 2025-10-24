#!/usr/bin/env python3
"""
Download crime data from Boston's open data portal
"""

import requests
import pandas as pd
import json
import os
from datetime import datetime
import time

def get_crime_incident_reports(limit=5000, offset=0):
    """
    Download crime incident reports from Boston's open data portal
    """
    print("🔍 Fetching crime incident reports from Boston Open Data Portal...")
    
    # Crime incident reports resource ID (2023 to present)
    resource_id = "b973d8cb-eeb2-4e7e-99da-c92938efc9c0"
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
        filename = f"boston_crime_data_{timestamp}.csv"
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        df.to_csv(filepath, index=False)
        print(f"💾 Data saved to: {filepath}")
        
        # Print data info
        print(f"📈 Data shape: {df.shape}")
        if 'OCCURRED_ON_DATE' in df.columns:
            print(f"📅 Date range: {df['OCCURRED_ON_DATE'].min()} to {df['OCCURRED_ON_DATE'].max()}")
        if 'DISTRICT' in df.columns:
            print(f"🏘️ Districts: {df['DISTRICT'].unique()}")
        if 'OFFENSE_CODE_GROUP' in df.columns:
            print(f"🔍 Offense types: {df['OFFENSE_CODE_GROUP'].value_counts().head()}")
        
        return df, filepath
    else:
        print("❌ No data fetched")
        return None, None

def filter_shots_fired_data(df):
    """
    Filter for shots fired incidents
    """
    print("🔫 Filtering for shots fired incidents...")
    
    if 'OFFENSE_CODE_GROUP' not in df.columns:
        print("❌ OFFENSE_CODE_GROUP column not found")
        return None, None
    
    # Filter for shots fired incidents
    shots_fired = df[df['OFFENSE_CODE_GROUP'].str.contains('SHOTS', case=False, na=False)]
    
    if shots_fired.empty:
        print("❌ No shots fired incidents found")
        return None, None
    
    print(f"🔫 Found {len(shots_fired)} shots fired incidents")
    
    # Save shots fired data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"boston_shots_fired_{timestamp}.csv"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    shots_fired.to_csv(filepath, index=False)
    print(f"💾 Shots fired data saved to: {filepath}")
    
    return shots_fired, filepath

def filter_homicide_data(df):
    """
    Filter for homicide incidents
    """
    print("💀 Filtering for homicide incidents...")
    
    if 'OFFENSE_CODE_GROUP' not in df.columns:
        print("❌ OFFENSE_CODE_GROUP column not found")
        return None, None
    
    # Filter for homicide incidents
    homicides = df[df['OFFENSE_CODE_GROUP'].str.contains('HOMICIDE', case=False, na=False)]
    
    if homicides.empty:
        print("❌ No homicide incidents found")
        return None, None
    
    print(f"💀 Found {len(homicides)} homicide incidents")
    
    # Save homicide data
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"boston_homicide_{timestamp}.csv"
    filepath = os.path.join(os.path.dirname(__file__), filename)
    
    homicides.to_csv(filepath, index=False)
    print(f"💾 Homicide data saved to: {filepath}")
    
    return homicides, filepath

if __name__ == "__main__":
    print("🚨 Boston Crime Data Downloader")
    print("=" * 40)
    
    # Download all crime data
    df_all, filepath_all = get_crime_incident_reports()
    
    if df_all is not None:
        print("\n" + "=" * 40)
        print("🔫 Filtering for shots fired incidents...")
        df_shots, filepath_shots = filter_shots_fired_data(df_all)
        
        print("\n" + "=" * 40)
        print("💀 Filtering for homicide incidents...")
        df_homicide, filepath_homicide = filter_homicide_data(df_all)
        
        print("\n✅ Download complete!")
        print(f"📁 All crime data: {filepath_all}")
        if filepath_shots:
            print(f"🔫 Shots fired: {filepath_shots}")
        if filepath_homicide:
            print(f"💀 Homicide: {filepath_homicide}")
    else:
        print("❌ Download failed")
