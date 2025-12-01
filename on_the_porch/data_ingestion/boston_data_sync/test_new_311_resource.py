#!/usr/bin/env python3
"""Test the new 311 resource ID to verify API and field names"""

import requests
import json

BOSTON_CKAN_API = "https://data.boston.gov/api/3/action"

# The resource ID from the URL provided
resource_id = "254adca6-64ab-4c5c-9fc0-a6da622be185"

print(f"Testing 311 resource: {resource_id}\n")
print(f"URL: https://data.boston.gov/dataset/311-service-requests/resource/{resource_id}\n")

try:
    url = f"{BOSTON_CKAN_API}/datastore_search"
    params = {'resource_id': resource_id, 'limit': 5}
    response = requests.get(url, params=params, timeout=30)
    data = response.json()
    
    if data.get('success'):
        result = data.get('result', {})
        total = result.get('total', 0)
        print(f"✅ API accessible")
        print(f"   Total records: {total:,}")
        
        records = result.get('records', [])
        if records:
            print(f"\n   Sample record fields:")
            sample = records[0]
            for key, value in list(sample.items())[:20]:  # First 20 fields
                value_str = str(value)[:50] if value else 'None'
                if len(str(value)) > 50:
                    value_str += '...'
                print(f"     - {key}: {value_str}")
            
            if len(sample) > 20:
                print(f"     ... and {len(sample) - 20} more fields")
            
            # Check for key fields
            print(f"\n   Key field check:")
            key_fields = {
                'case_id': ['case_id', 'case_enquiry_id', 'id'],
                'date_field': ['open_date', 'open_dt', 'created_date'],
                'type': ['type', 'case_topic', 'service_name', 'reason']
            }
            
            for field_type, possible_names in key_fields.items():
                found = None
                for name in possible_names:
                    if name in sample:
                        found = name
                        break
                if found:
                    print(f"     ✅ {field_type}: '{found}'")
                else:
                    print(f"     ❌ {field_type}: Not found (checked: {', '.join(possible_names)})")
            
            # Check date range
            if 'open_date' in sample or 'open_dt' in sample:
                date_field = 'open_date' if 'open_date' in sample else 'open_dt'
                params_asc = {'resource_id': resource_id, 'limit': 1, 'sort': f'{date_field} asc'}
                resp_first = requests.get(url, params=params_asc, timeout=10)
                if resp_first.status_code == 200:
                    first_data = resp_first.json()
                    if first_data.get('success') and first_data.get('result', {}).get('records'):
                        first_date = first_data['result']['records'][0].get(date_field, 'N/A')
                        print(f"\n   📅 First record date ({date_field}): {first_date}")
                
                params_desc = {'resource_id': resource_id, 'limit': 1, 'sort': f'{date_field} desc'}
                resp_last = requests.get(url, params=params_desc, timeout=10)
                if resp_last.status_code == 200:
                    last_data = resp_last.json()
                    if last_data.get('success') and last_data.get('result', {}).get('records'):
                        last_date = last_data['result']['records'][0].get(date_field, 'N/A')
                        print(f"   📅 Last record date ({date_field}): {last_date}")
    else:
        print(f"❌ API Error: {data.get('error', 'Unknown error')}")
        if isinstance(data.get('error'), dict):
            print(f"   Details: {json.dumps(data.get('error'), indent=2)}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

