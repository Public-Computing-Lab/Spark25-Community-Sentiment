"""
Quick test script for api_v2.py endpoints.
Run this while the API server is running on port 8888.
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8888"

def test_health():
    print("\n=== Testing /health ===")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    return resp.status_code == 200

def test_events():
    print("\n=== Testing /events ===")
    resp = requests.get(f"{BASE_URL}/events", params={"limit": 3, "days_ahead": 14})
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Total events: {data.get('total', 0)}")
    if data.get("events"):
        print(f"First event: {data['events'][0].get('event_name', 'N/A')}")
    return resp.status_code == 200

def test_log_post():
    print("\n=== Testing /log (POST) ===")
    payload = {
        "client_query": "Test question from test script",
        "app_response": "Test answer from test script",
        "mode": "test"
    }
    resp = requests.post(f"{BASE_URL}/log", json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    return resp.status_code == 201

def test_chat():
    print("\n=== Testing /chat ===")
    payload = {
        "message": "What events are happening this week?",
        "conversation_history": []
    }
    print("Sending chat request (this may take a few seconds)...")
    resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=60)
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"Mode: {data.get('mode', 'N/A')}")
    print(f"Sources: {data.get('sources', [])}")
    response_text = data.get('response', '')
    print(f"Response (first 200 chars): {response_text[:200]}...")
    return resp.status_code == 200

if __name__ == "__main__":
    print("Testing API v2 endpoints...")
    
    results = []
    
    # Test health
    results.append(("Health", test_health()))
    
    # Test events
    results.append(("Events", test_events()))
    
    # Test log
    results.append(("Log POST", test_log_post()))
    
    # Test chat (optional - can be slow)
    try:
        results.append(("Chat", test_chat()))
    except Exception as e:
        print(f"\n=== Chat test failed: {e} ===")
        results.append(("Chat", False))
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name}: {status}")

