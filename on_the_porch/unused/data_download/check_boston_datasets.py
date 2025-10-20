#!/usr/bin/env python3
"""
Check what datasets are available on Boston's data portal
"""

import requests
import json

def check_available_datasets():
    """Check what datasets are available"""
    print("🔍 Checking available datasets on Boston's data portal...")
    
    # Get list of all packages
    url = "https://data.boston.gov/api/3/action/package_list"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data['success']:
            packages = data['result']
            print(f"📊 Found {len(packages)} datasets")
            
            # Look for crime-related datasets
            crime_keywords = ['crime', 'incident', '911', 'police', 'shooting', 'homicide']
            crime_datasets = []
            
            for package in packages:
                if any(keyword in package.lower() for keyword in crime_keywords):
                    crime_datasets.append(package)
            
            print(f"\n🔍 Crime-related datasets found:")
            for dataset in crime_datasets:
                print(f"  - {dataset}")
            
            return crime_datasets
        else:
            print(f"❌ API Error: {data['error']}")
            return []
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def get_dataset_info(dataset_name):
    """Get detailed info about a specific dataset"""
    print(f"\n📋 Getting info for dataset: {dataset_name}")
    
    url = "https://data.boston.gov/api/3/action/package_show"
    params = {'id': dataset_name}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data['success']:
            dataset_info = data['result']
            print(f"📝 Title: {dataset_info.get('title', 'N/A')}")
            print(f"📄 Description: {dataset_info.get('notes', 'N/A')[:200]}...")
            
            # Get resource info
            resources = dataset_info.get('resources', [])
            print(f"📊 Resources: {len(resources)}")
            
            for i, resource in enumerate(resources):
                print(f"  Resource {i+1}:")
                print(f"    Name: {resource.get('name', 'N/A')}")
                print(f"    Format: {resource.get('format', 'N/A')}")
                print(f"    ID: {resource.get('id', 'N/A')}")
                print(f"    URL: {resource.get('url', 'N/A')}")
            
            return dataset_info
        else:
            print(f"❌ Error getting dataset info: {data['error']}")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_resource_access(resource_id):
    """Test if we can access a specific resource"""
    print(f"\n🧪 Testing access to resource: {resource_id}")
    
    url = "https://data.boston.gov/api/3/action/datastore_search"
    params = {
        'resource_id': resource_id,
        'limit': 5
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        if data['success']:
            records = data['result']['records']
            print(f"✅ Success! Found {len(records)} records")
            if records:
                print(f"📋 Sample record fields: {list(records[0].keys())}")
            return True
        else:
            print(f"❌ API Error: {data['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Boston Data Portal Dataset Checker")
    print("=" * 50)
    
    # Check available datasets
    crime_datasets = check_available_datasets()
    
    if crime_datasets:
        print(f"\n📋 Found {len(crime_datasets)} crime-related datasets")
        
        # Get info for each dataset
        for dataset in crime_datasets[:3]:  # Check first 3
            dataset_info = get_dataset_info(dataset)
            
            if dataset_info:
                resources = dataset_info.get('resources', [])
                for resource in resources:
                    resource_id = resource.get('id')
                    if resource_id:
                        test_resource_access(resource_id)
    else:
        print("❌ No crime-related datasets found")
