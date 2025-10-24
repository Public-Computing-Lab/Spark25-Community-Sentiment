#!/usr/bin/env python3
"""
Get the correct resource ID for crime incident reports
"""

import requests
import json

def get_crime_resource_id():
    """Get the resource ID for crime incident reports"""
    print("Finding crime incident reports dataset...")
    
    # Get the package info for crime incident reports
    url = "https://data.boston.gov/api/3/action/package_show"
    params = {'id': 'crime-incident-reports-august-2015-to-date-source-new-system'}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data['success']:
            dataset_info = data['result']
            print(f"Dataset: {dataset_info.get('title', 'N/A')}")
            
            # Get resource info
            resources = dataset_info.get('resources', [])
            print(f"Resources: {len(resources)}")
            
            for i, resource in enumerate(resources):
                print(f"Resource {i+1}:")
                print(f"  Name: {resource.get('name', 'N/A')}")
                print(f"  Format: {resource.get('format', 'N/A')}")
                print(f"  ID: {resource.get('id', 'N/A')}")
                
                # Test this resource
                resource_id = resource.get('id')
                if resource_id:
                    test_url = "https://data.boston.gov/api/3/action/datastore_search"
                    test_params = {'resource_id': resource_id, 'limit': 5}
                    
                    test_response = requests.get(test_url, params=test_params, timeout=30)
                    if test_response.status_code == 200:
                        test_data = test_response.json()
                        if test_data['success']:
                            records = test_data['result']['records']
                            print(f"  ✅ Working! Found {len(records)} records")
                            if records:
                                print(f"  Fields: {list(records[0].keys())}")
                            return resource_id
                        else:
                            print(f"  ❌ API Error: {test_data['error']}")
                    else:
                        print(f"  ❌ HTTP Error: {test_response.status_code}")
            
            return None
        else:
            print(f"Error: {data['error']}")
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    resource_id = get_crime_resource_id()
    if resource_id:
        print(f"\n✅ Correct resource ID: {resource_id}")
    else:
        print("\n❌ Could not find working resource ID")
