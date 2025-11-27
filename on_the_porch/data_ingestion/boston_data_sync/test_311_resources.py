#!/usr/bin/env python3
"""Test 311 resource IDs to find the one with the most data"""

import requests
import json

BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"

# Test resource IDs from config
resource_ids = {
    "2020": "6ff6a6fd-3141-4440-a880-6f60a37fe789",
    "2021": "f53ebccd-bc61-49f9-83db-625f209c95f5",
    "2022": "81a7b022-f8fc-4da5-80e4-b160058ca207",
    "2023": "e6013a93-1321-4f2a-bf91-8d8a02f1e62f",
    "2024": "dff4d804-5031-443a-8409-8344efd0e5c8",
}

print("Testing 311 resource IDs:\n")

for year, resource_id in resource_ids.items():
    try:
        url = f"{BOSTON_CKAN_API}/datastore_search"
        params = {'resource_id': resource_id, 'limit': 1}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get('success'):
            total = data.get('result', {}).get('total', 0)
            print(f"{year}: {resource_id}")
            print(f"  Total records: {total:,}")
            
            # Get date range if available
            if total > 0:
                # Get first and last record dates
                params_all = {'resource_id': resource_id, 'limit': 1, 'sort': 'open_dt asc'}
                resp_first = requests.get(url, params=params_all, timeout=10)
                if resp_first.status_code == 200:
                    first_data = resp_first.json()
                    if first_data.get('success') and first_data.get('result', {}).get('records'):
                        first_date = first_data['result']['records'][0].get('open_dt', 'N/A')
                        print(f"  First record date: {first_date}")
                
                params_all = {'resource_id': resource_id, 'limit': 1, 'sort': 'open_dt desc'}
                resp_last = requests.get(url, params=params_all, timeout=10)
                if resp_last.status_code == 200:
                    last_data = resp_last.json()
                    if last_data.get('success') and last_data.get('result', {}).get('records'):
                        last_date = last_data['result']['records'][0].get('open_dt', 'N/A')
                        print(f"  Last record date: {last_date}")
        else:
            print(f"{year}: {resource_id}")
            print(f"  ERROR: {data.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"{year}: {resource_id}")
        print(f"  ERROR: {e}")
    print()

