#!/usr/bin/env python3
"""Quick script to find 311 service requests resource ID"""

import requests
import json

BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"

# Search for 311 datasets
url = f"{BOSTON_CKAN_API}/package_search"
params = {'q': '311', 'rows': 20}

response = requests.get(url, params=params, timeout=30)
data = response.json()

print("Found 311 datasets:\n")
for dataset in data.get('result', {}).get('results', []):
    print(f"Title: {dataset.get('title')}")
    print(f"ID: {dataset.get('id')}")
    
    # Get resources
    package_url = f"{BOSTON_CKAN_API}/package_show"
    package_params = {'id': dataset.get('id')}
    package_resp = requests.get(package_url, params=package_params, timeout=30)
    package_data = package_resp.json()
    
    if package_data.get('success'):
        resources = package_data['result'].get('resources', [])
        print(f"Resources ({len(resources)}):")
        for res in resources:
            print(f"  - {res.get('name', 'Unnamed')}")
            print(f"    Resource ID: {res.get('id')}")
            print(f"    Format: {res.get('format')}")
            print(f"    Datastore Active: {res.get('datastore_active', False)}")
            
            # Test if accessible
            test_url = f"{BOSTON_CKAN_API}/datastore_search"
            test_params = {'resource_id': res.get('id'), 'limit': 1}
            test_resp = requests.get(test_url, params=test_params, timeout=10)
            if test_resp.status_code == 200:
                test_data = test_resp.json()
                if test_data.get('success'):
                    count = test_data.get('result', {}).get('total', 0)
                    print(f"    ✅ Accessible via API - Total records: {count}")
    print("\n" + "="*60 + "\n")

