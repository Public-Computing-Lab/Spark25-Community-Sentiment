"""
Authenticated smoke test for api_v2.py.

Run this while the API server is running locally.
The script exercises the new session-backed flow:
- health
- auth bootstrap
- signup
- auth/me
- conversation create + fetch
- optional chat message send
- events
- logout + login
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Any

import requests

BASE_URL = os.getenv("OTP_API_BASE_URL", "http://127.0.0.1:8888")
RUN_CHAT_TEST = os.getenv("OTP_RUN_CHAT_TEST", "0") == "1"
REQUEST_TIMEOUT = int(os.getenv("OTP_REQUEST_TIMEOUT", "60"))


def pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def csrf_headers(session: requests.Session) -> dict[str, str]:
    token = session.cookies.get("otp_csrf", "")
    return {"X-CSRF-Token": token} if token else {}


def bootstrap_session(session: requests.Session) -> bool:
    print("\n=== Bootstrapping CSRF cookie via /auth/me ===")
    response = session.get(f"{BASE_URL}/auth/me", timeout=REQUEST_TIMEOUT)
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 200 and bool(session.cookies.get("otp_csrf"))


def test_health() -> bool:
    print("\n=== Testing /health ===")
    response = requests.get(f"{BASE_URL}/health", timeout=REQUEST_TIMEOUT)
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 200


def test_signup(session: requests.Session) -> tuple[bool, str, str]:
    print("\n=== Testing /auth/signup ===")
    suffix = secrets.token_hex(4)
    email = f"otp-auth-{suffix}@example.com"
    password = f"StablePass-{suffix}-2026"
    payload = {
        "email": email,
        "username": f"otp_{suffix}",
        "password": password,
    }
    response = session.post(
        f"{BASE_URL}/auth/signup",
        json=payload,
        headers=csrf_headers(session),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 201, email, password


def test_auth_me(session: requests.Session) -> bool:
    print("\n=== Testing /auth/me after signup/login ===")
    response = session.get(f"{BASE_URL}/auth/me", timeout=REQUEST_TIMEOUT)
    print(f"Status: {response.status_code}")
    data = response.json()
    print(pretty(data))
    return response.status_code == 200 and data.get("authenticated") is True


def test_create_conversation(session: requests.Session) -> tuple[bool, str]:
    print("\n=== Testing /conversations (POST) ===")
    response = session.post(
        f"{BASE_URL}/conversations",
        json={"title": "Auth smoke test"},
        headers=csrf_headers(session),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(pretty(data))
    thread_id = data.get("thread", {}).get("id", "")
    return response.status_code == 201 and bool(thread_id), thread_id


def test_fetch_messages(session: requests.Session, thread_id: str) -> bool:
    print("\n=== Testing /conversations/:id/messages (GET) ===")
    response = session.get(
        f"{BASE_URL}/conversations/{thread_id}/messages",
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 200


def test_post_message(session: requests.Session, thread_id: str) -> bool:
    print("\n=== Testing /conversations/:id/messages (POST) ===")
    payload = {"message": "What events are happening this week?"}
    response = session.post(
        f"{BASE_URL}/conversations/{thread_id}/messages",
        json=payload,
        headers=csrf_headers(session),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(pretty({
        "thread": data.get("thread"),
        "assistant_message_preview": (data.get("assistant_message", {}).get("content") or "")[:200],
    }))
    return response.status_code == 201


def test_events(session: requests.Session) -> bool:
    print("\n=== Testing /events ===")
    response = session.get(
        f"{BASE_URL}/events",
        params={"limit": 3, "days_ahead": 14},
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(pretty({"total": data.get("total"), "events": data.get("events", [])[:1]}))
    return response.status_code == 200


def test_logout(session: requests.Session) -> bool:
    print("\n=== Testing /auth/logout ===")
    response = session.post(
        f"{BASE_URL}/auth/logout",
        json={},
        headers=csrf_headers(session),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 200


def test_login(session: requests.Session, email: str, password: str) -> bool:
    print("\n=== Testing /auth/login ===")
    bootstrap_session(session)
    response = session.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(session),
        timeout=REQUEST_TIMEOUT,
    )
    print(f"Status: {response.status_code}")
    print(pretty(response.json()))
    return response.status_code == 200


if __name__ == "__main__":
    print(f"Testing API v2 endpoints at {BASE_URL}...")
    results: list[tuple[str, bool]] = []
    client = requests.Session()

    results.append(("Health", test_health()))
    results.append(("Auth bootstrap", bootstrap_session(client)))

    signup_ok, email, password = test_signup(client)
    results.append(("Signup", signup_ok))
    results.append(("Auth /me", test_auth_me(client)))

    thread_ok, thread_id = test_create_conversation(client)
    results.append(("Create conversation", thread_ok))
    if thread_id:
        results.append(("Fetch messages", test_fetch_messages(client, thread_id)))
        if RUN_CHAT_TEST:
            results.append(("Send message", test_post_message(client, thread_id)))
        else:
            print("\n=== Skipping conversation message send (set OTP_RUN_CHAT_TEST=1 to enable) ===")

    results.append(("Events", test_events(client)))
    results.append(("Logout", test_logout(client)))
    results.append(("Login", test_login(client, email, password)))
    results.append(("Auth /me after login", test_auth_me(client)))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")
