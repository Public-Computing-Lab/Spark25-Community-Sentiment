#!/usr/bin/env python3
"""
Helper script to find resource IDs for Boston Open Data Portal datasets.

Usage:
    python find_boston_resource_id.py <dataset_name_or_url>
    
Example:
    python find_boston_resource_id.py "crime incident reports"
    python find_boston_resource_id.py "311 service requests"
"""

import sys
import requests
import json
from typing import Optional, List, Dict

BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"


def search_datasets(query: str) -> List[Dict]:
    """Search for datasets matching the query."""
    url = f"{BOSTON_CKAN_API}/package_search"
    params = {'q': query, 'rows': 20}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            return data['result']['results']
        return []
    except Exception as e:
        print(f"❌ Error searching: {e}")
        return []


def get_package_resources(package_id: str) -> List[Dict]:
    """Get all resources for a package."""
    url = f"{BOSTON_CKAN_API}/package_show"
    params = {'id': package_id}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get('success'):
            return data['result'].get('resources', [])
        return []
    except Exception as e:
        print(f"❌ Error fetching package: {e}")
        return []


def test_resource(resource_id: str) -> bool:
    """Test if a resource is accessible via datastore API."""
    url = f"{BOSTON_CKAN_API}/datastore_search"
    params = {'resource_id': resource_id, 'limit': 1}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('success', False)
    except:
        return False


def find_resource_id(query: str) -> Optional[str]:
    """Find resource ID for a dataset query."""
    print(f"🔍 Searching for: {query}\n")
    
    # Search for datasets
    datasets = search_datasets(query)
    
    if not datasets:
        print("❌ No datasets found")
        return None
    
    print(f"📋 Found {len(datasets)} dataset(s):\n")
    
    for i, dataset in enumerate(datasets, 1):
        print(f"{i}. {dataset.get('title', 'Untitled')}")
        print(f"   ID: {dataset.get('id', 'N/A')}")
        print(f"   Organization: {dataset.get('organization', {}).get('title', 'N/A')}")
        print()
    
    # Get resources for first dataset (or let user choose)
    if len(datasets) == 1:
        selected = datasets[0]
    else:
        print("Using first dataset. For others, run with the specific dataset ID.\n")
        selected = datasets[0]
    
    print(f"📦 Getting resources for: {selected.get('title')}\n")
    resources = get_package_resources(selected['id'])
    
    if not resources:
        print("❌ No resources found in this dataset")
        return None
    
    # Find datastore resources (those accessible via API)
    datastore_resources = []
    for resource in resources:
        if resource.get('datastore_active') or test_resource(resource.get('id', '')):
            datastore_resources.append(resource)
    
    if not datastore_resources:
        print("⚠️  No datastore resources found (resources not accessible via API)")
        print("\nAvailable resources:")
        for resource in resources:
            print(f"   - {resource.get('name', 'Unnamed')} ({resource.get('format', 'N/A')})")
        return None
    
    print(f"✅ Found {len(datastore_resources)} datastore resource(s):\n")
    
    for i, resource in enumerate(datastore_resources, 1):
        print(f"{i}. {resource.get('name', 'Unnamed Resource')}")
        print(f"   Resource ID: {resource.get('id')}")
        print(f"   Format: {resource.get('format', 'N/A')}")
        print(f"   Description: {resource.get('description', 'N/A')[:100]}...")
        print()
    
    # Return first resource ID
    if datastore_resources:
        resource_id = datastore_resources[0].get('id')
        print(f"✅ Recommended Resource ID: {resource_id}\n")
        print("Add this to your boston_datasets_config.json:")
        print(f'  "resource_id": "{resource_id}"')
        return resource_id
    
    return None


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python find_boston_resource_id.py <dataset_name_or_url>")
        print("\nExample:")
        print('  python find_boston_resource_id.py "crime incident reports"')
        print('  python find_boston_resource_id.py "311 service requests"')
        sys.exit(1)
    
    query = ' '.join(sys.argv[1:])
    resource_id = find_resource_id(query)
    
    if resource_id:
        print(f"\n✅ Resource ID found: {resource_id}")
    else:
        print("\n❌ Could not find resource ID")
        sys.exit(1)


if __name__ == "__main__":
    main()

