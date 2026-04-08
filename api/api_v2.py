"""
api_v2.py

Authenticated API for the Dorchester community chatbot.
Supports password auth, Google OAuth, role-based admin access,
and per-user conversation threads backed by MySQL.
"""

from __future__ import annotations

import datetime
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin

from dotenv import load_dotenv
from flask import Flask, g, has_request_context, jsonify, redirect, request, session
from flask_cors import CORS
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

try:
    from authlib.integrations.flask_client import OAuth
except ImportError:  # pragma: no cover - dependency is enforced via requirements
    OAuth = None

from db_migrations import run_migrations
from security import (
    generate_token,
    get_client_ip,
    get_token_secret,
    hash_password,
    hash_token,
    is_safe_next_path,
    json_dumps,
    json_loads,
    normalize_email,
    normalize_username,
    serialize_user,
    summarize_thread_title,
    utcnow,
    validate_password,
    validate_username,
    verify_password,
)

# Setup paths to import from on_the_porch
_THIS_FILE = Path(__file__).resolve()
_API_DIR = _THIS_FILE.parent
_ROOT_DIR = _API_DIR.parent
load_dotenv(_ROOT_DIR / ".env")
_ON_THE_PORCH_DIR = _ROOT_DIR / "on_the_porch"

if str(_ON_THE_PORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ON_THE_PORCH_DIR))

_RAG_DIR = _ON_THE_PORCH_DIR / "rag stuff"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

from unified_chatbot import (  # noqa: E402
    _answer_from_history,
    _bootstrap_env,
    _check_if_needs_new_data,
    _fix_retrieval_vectordb_path,
    _route_question,
    _run_hybrid,
    _run_rag,
    _run_sql,
    build_retrieval_cache,
    create_empty_cache,
)

_bootstrap_env()
_fix_retrieval_vectordb_path()

_legacy_session_caches: Dict[str, Dict[str, Any]] = {}
_CACHE_MAX_SESSIONS = 100
_CACHE_MAX_AGE_MINUTES = 60


class Config:
    API_VERSION = "v3.0"

    _raw_keys = os.getenv("RETHINKAI_API_KEYS", "").split(",")
    RETHINKAI_API_KEYS = [key.strip() for key in _raw_keys if key.strip()]

    HOST = os.getenv("API_HOST", "127.0.0.1")
    PORT = int(os.getenv("API_PORT", "8888"))

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "agent-api-secret-2025")
    SESSION_COOKIE_SECURE = os.getenv("FLASK_SESSION_COOKIE_SECURE", "False").lower() == "true"
    AUTH_SESSION_COOKIE_NAME = os.getenv("AUTH_SESSION_COOKIE_NAME", "otp_session")
    AUTH_CSRF_COOKIE_NAME = os.getenv("AUTH_CSRF_COOKIE_NAME", "otp_csrf")
    SESSION_MAX_AGE_DAYS = int(os.getenv("AUTH_SESSION_MAX_AGE_DAYS", "7"))
    SESSION_SAMESITE = os.getenv("AUTH_SESSION_SAMESITE", "Lax")

    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    API_BASE_URL = os.getenv("API_BASE_URL", f"http://{HOST}:{PORT}")
    _allowed_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins if origin.strip()]

    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB = os.getenv("MYSQL_DB", "rethink_ai_boston")

    LOGIN_WINDOW_MINUTES = int(os.getenv("AUTH_LOGIN_WINDOW_MINUTES", "15"))
    LOGIN_LOCK_THRESHOLD = int(os.getenv("AUTH_LOGIN_LOCK_THRESHOLD", "5"))
    LOGIN_LOCK_MINUTES = int(os.getenv("AUTH_LOGIN_LOCK_MINUTES", "15"))
    _raw_admin_emails = os.getenv("AUTH_ADMIN_EMAILS", "").split(",")
    AUTH_ADMIN_EMAILS = {normalize_email(email) for email in _raw_admin_emails if normalize_email(email)}

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_DISCOVERY_URL = os.getenv(
        "GOOGLE_OAUTH_DISCOVERY_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        f"{API_BASE_URL}/auth/google/callback",
    )


DOC_TYPE_DIRS = {
    "policy": urljoin(Config.APP_BASE_URL.rstrip("/") + "/", "Policies/"),
    "transcript": "Data/AI meeting transcripts",
    "calendar_event": "Data/newsletters",
}


db_pool = MySQLConnectionPool(
    host=Config.MYSQL_HOST,
    port=Config.MYSQL_PORT,
    user=Config.MYSQL_USER,
    password=Config.MYSQL_PASSWORD,
    database=Config.MYSQL_DB,
    pool_name="api_v2_pool",
    pool_size=10,
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=Config.SECRET_KEY,
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=Config.SESSION_MAX_AGE_DAYS),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE=Config.SESSION_SAMESITE,
)

CORS(
    app,
    supports_credentials=True,
    resources={r"/*": {"origins": Config.ALLOWED_ORIGINS}},
    allow_headers=["Content-Type", "X-CSRF-Token", "RethinkAI-API-Key"],
)

oauth = None
if OAuth and Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET:
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=Config.GOOGLE_CLIENT_SECRET,
        server_metadata_url=Config.GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile"},
    )


def get_db_connection():
    return db_pool.get_connection()


def initialize_database() -> None:
    run_migrations(get_db_connection)


initialize_database()


def _bootstrap_admin_users() -> None:
    if not Config.AUTH_ADMIN_EMAILS:
        return

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        placeholders = ", ".join(["%s"] * len(Config.AUTH_ADMIN_EMAILS))
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE users
            SET role = 'admin'
            WHERE email IN ({placeholders}) AND role <> 'admin'
            """,
            tuple(sorted(Config.AUTH_ADMIN_EMAILS)),
        )
        conn.commit()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


_bootstrap_admin_users()


def _cleanup_old_legacy_caches() -> None:
    if len(_legacy_session_caches) <= _CACHE_MAX_SESSIONS:
        return

    now = datetime.datetime.now()
    stale_keys = []
    for sid, cache in _legacy_session_caches.items():
        timestamp = cache.get("timestamp")
        if not timestamp:
            continue
        try:
            cache_time = datetime.datetime.fromisoformat(timestamp)
        except Exception:
            continue
        age_minutes = (now - cache_time).total_seconds() / 60
        if age_minutes > _CACHE_MAX_AGE_MINUTES:
            stale_keys.append(sid)

    for sid in stale_keys:
        _legacy_session_caches.pop(sid, None)

    if len(_legacy_session_caches) > _CACHE_MAX_SESSIONS:
        sorted_sessions = sorted(
            _legacy_session_caches.items(),
            key=lambda item: item[1].get("timestamp", ""),
        )
        overflow = len(_legacy_session_caches) - _CACHE_MAX_SESSIONS
        for sid, _ in sorted_sessions[:overflow]:
            _legacy_session_caches.pop(sid, None)


# =============================================================================
# Utility helpers
# =============================================================================

DOC_TYPE_DIRS = {
    "policy": "http://localhost:8000/Policies/",
    "transcript": "Data/AI meeting transcripts",
    "calendar_event": "Data/newsletters",
}
def _cookie_kwargs(*, httponly: bool, expires: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "httponly": httponly,
        "secure": Config.SESSION_COOKIE_SECURE,
        "samesite": Config.SESSION_SAMESITE,
        "path": "/",
    }
    if expires is not None:
        kwargs["expires"] = expires
    return kwargs


def _set_auth_cookies(response, session_token: str, csrf_token: str, expires_at: datetime.datetime) -> None:
    response.set_cookie(
        Config.AUTH_SESSION_COOKIE_NAME,
        session_token,
        **_cookie_kwargs(httponly=True, expires=expires_at),
    )
    response.set_cookie(
        Config.AUTH_CSRF_COOKIE_NAME,
        csrf_token,
        **_cookie_kwargs(httponly=False, expires=expires_at),
    )
    g.csrf_cookie_written = True



def _clear_auth_cookies(response) -> None:
    response.delete_cookie(Config.AUTH_SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(Config.AUTH_CSRF_COOKIE_NAME, path="/")
    g.csrf_cookie_written = True



def _json_error(message: str, status: int, code: Optional[str] = None):
    payload = {"error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status



def _provider_names(conn, user_id: str) -> List[str]:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT provider FROM auth_identities WHERE user_id = %s", (user_id,))
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()



def _fetch_user_by_id(conn, user_id: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s LIMIT 1", (user_id,))
        return cursor.fetchone()
    finally:
        cursor.close()



def _fetch_user_by_email(conn, email: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE email = %s LIMIT 1", (email,))
        return cursor.fetchone()
    finally:
        cursor.close()



def _fetch_user_by_username(conn, username: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE username = %s LIMIT 1", (username,))
        return cursor.fetchone()
    finally:
        cursor.close()



def _fetch_password_login_row(conn, email: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT ai.id AS identity_id, ai.password_hash, ai.last_used_at,
                   u.id, u.email, u.username, u.role, u.status,
                   u.profile_complete, u.created_at, u.updated_at, u.last_login_at
            FROM auth_identities ai
            JOIN users u ON u.id = ai.user_id
            WHERE ai.provider = 'password' AND u.email = %s
            LIMIT 1
            """,
            (email,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _fetch_google_user_by_subject(conn, provider_subject: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT u.*
            FROM auth_identities ai
            JOIN users u ON u.id = ai.user_id
            WHERE ai.provider = 'google' AND ai.provider_subject = %s
            LIMIT 1
            """,
            (provider_subject,),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _fetch_identity_for_user(conn, user_id: str, provider: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM auth_identities WHERE user_id = %s AND provider = %s LIMIT 1",
            (user_id, provider),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _create_user(conn, email: str, username: str, *, profile_complete: bool) -> Dict[str, Any]:
    user_id = str(uuid.uuid4())
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (id, email, username, role, status, profile_complete)
            VALUES (%s, %s, %s, 'user', 'active', %s)
            """,
            (user_id, email, username, profile_complete),
        )
    finally:
        cursor.close()
    return _fetch_user_by_id(conn, user_id)


def _should_promote_to_admin(email: str) -> bool:
    return normalize_email(email) in Config.AUTH_ADMIN_EMAILS


def _promote_user_to_admin_if_configured(
    conn,
    *,
    user_id: str,
    email: str,
    current_role: Optional[str] = None,
    audit_event: Optional[str] = None,
) -> bool:
    if not _should_promote_to_admin(email):
        return False
    if current_role == "admin":
        return False

    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET role = 'admin' WHERE id = %s AND role <> 'admin'",
            (user_id,),
        )
        updated = cursor.rowcount > 0
    finally:
        cursor.close()

    if updated and audit_event and has_request_context():
        _record_auth_event(
            conn,
            audit_event,
            success=True,
            user_id=user_id,
            details={"email": normalize_email(email), "source": "AUTH_ADMIN_EMAILS"},
        )
    return updated



def _create_auth_identity(
    conn,
    *,
    user_id: str,
    provider: str,
    provider_subject: Optional[str] = None,
    password_hash_value: Optional[str] = None,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO auth_identities (id, user_id, provider, provider_subject, password_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), user_id, provider, provider_subject, password_hash_value),
        )
    finally:
        cursor.close()



def _update_user_login_stamp(conn, user_id: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE users SET last_login_at = %s WHERE id = %s",
            (utcnow(), user_id),
        )
    finally:
        cursor.close()



def _update_identity_last_used(conn, user_id: str, provider: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE auth_identities SET last_used_at = %s WHERE user_id = %s AND provider = %s",
            (utcnow(), user_id, provider),
        )
    finally:
        cursor.close()



def _update_password_hash(conn, identity_id: str, new_password_hash: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE auth_identities SET password_hash = %s WHERE id = %s",
            (new_password_hash, identity_id),
        )
    finally:
        cursor.close()



def _create_web_session(conn, user_id: str) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    session_token = generate_token(32)
    csrf_token = generate_token(24)
    expires_at = utcnow() + datetime.timedelta(days=Config.SESSION_MAX_AGE_DAYS)
    secret = get_token_secret()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO web_sessions (
                id, user_id, session_token_hash, csrf_token_hash,
                user_agent, ip_created, last_seen_at, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                user_id,
                hash_token(session_token, secret),
                hash_token(csrf_token, secret),
                request.headers.get("User-Agent", "")[:512],
                get_client_ip(request.headers, request.remote_addr),
                utcnow(),
                expires_at,
            ),
        )
    finally:
        cursor.close()
    return {
        "id": session_id,
        "session_token": session_token,
        "csrf_token": csrf_token,
        "expires_at": expires_at,
    }



def _revoke_session(conn, session_id: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE web_sessions SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
            (utcnow(), session_id),
        )
    finally:
        cursor.close()



def _current_session_row(conn, raw_session_token: str) -> Optional[Dict[str, Any]]:
    secret = get_token_secret()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT ws.id AS session_id, ws.user_id, ws.csrf_token_hash,
                   ws.expires_at, ws.revoked_at,
                   u.id, u.email, u.username, u.role, u.status,
                   u.profile_complete, u.created_at, u.updated_at, u.last_login_at
            FROM web_sessions ws
            JOIN users u ON u.id = ws.user_id
            WHERE ws.session_token_hash = %s
            LIMIT 1
            """,
            (hash_token(raw_session_token, secret),),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _touch_session(conn, session_id: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE web_sessions SET last_seen_at = %s WHERE id = %s",
            (utcnow(), session_id),
        )
    finally:
        cursor.close()



def _record_auth_event(
    conn,
    event_type: str,
    *,
    success: bool,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO auth_audit_log (user_id, event_type, success, ip_address, user_agent, details_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                event_type,
                success,
                get_client_ip(request.headers, request.remote_addr),
                request.headers.get("User-Agent", "")[:512],
                json_dumps(details or {}),
            ),
        )
    finally:
        cursor.close()



def _fetch_login_attempt(conn, email: str, ip_address: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM login_attempts WHERE normalized_email = %s AND ip_address = %s LIMIT 1",
            (email, ip_address),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _is_locked(record: Optional[Dict[str, Any]]) -> bool:
    return bool(record and record.get("locked_until") and record["locked_until"] > utcnow())



def _record_failed_login(conn, email: str, ip_address: str) -> Optional[datetime.datetime]:
    now = utcnow()
    record = _fetch_login_attempt(conn, email, ip_address)
    cursor = conn.cursor()
    try:
        if not record:
            failure_count = 1
            locked_until = now + datetime.timedelta(minutes=Config.LOGIN_LOCK_MINUTES) if failure_count >= Config.LOGIN_LOCK_THRESHOLD else None
            cursor.execute(
                """
                INSERT INTO login_attempts (
                    normalized_email, ip_address, failure_count,
                    first_attempt_at, last_attempt_at, locked_until
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (email, ip_address, failure_count, now, now, locked_until),
            )
            return locked_until

        first_attempt = record["first_attempt_at"]
        if first_attempt is None or (now - first_attempt).total_seconds() > Config.LOGIN_WINDOW_MINUTES * 60:
            failure_count = 1
            first_attempt = now
        else:
            failure_count = int(record.get("failure_count", 0)) + 1

        locked_until = now + datetime.timedelta(minutes=Config.LOGIN_LOCK_MINUTES) if failure_count >= Config.LOGIN_LOCK_THRESHOLD else None
        cursor.execute(
            """
            UPDATE login_attempts
            SET failure_count = %s,
                first_attempt_at = %s,
                last_attempt_at = %s,
                locked_until = %s
            WHERE normalized_email = %s AND ip_address = %s
            """,
            (failure_count, first_attempt, now, locked_until, email, ip_address),
        )
        return locked_until
    finally:
        cursor.close()



def _clear_login_attempts(conn, email: str, ip_address: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM login_attempts WHERE normalized_email = %s AND ip_address = %s",
            (email, ip_address),
        )
    finally:
        cursor.close()



def _build_oauth_redirect(path: str, error: Optional[str] = None) -> str:
    target = path if is_safe_next_path(path) else "/"
    if not error:
        return urljoin(Config.APP_BASE_URL.rstrip("/") + "/", target.lstrip("/"))
    joiner = "&" if "?" in target else "?"
    return urljoin(Config.APP_BASE_URL.rstrip("/") + "/", f"{target.lstrip('/')}" ) + f"{joiner}{urlencode({'auth_error': error})}"



def _enforce_csrf():
    if g.get("api_key_authenticated") and not g.get("current_user_row"):
        return None

    cookie_token = request.cookies.get(Config.AUTH_CSRF_COOKIE_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not header_token or cookie_token != header_token:
        return _json_error("CSRF validation failed.", 403, "csrf_failed")

    session_row = g.get("session_row")
    if session_row:
        expected_hash = session_row.get("csrf_token_hash")
        if expected_hash != hash_token(cookie_token, get_token_secret()):
            return _json_error("CSRF validation failed.", 403, "csrf_failed")

    return None



def _require_user(*, allow_incomplete: bool = False):
    current_user = g.get("current_user_row")
    if not current_user:
        return _json_error("Authentication required.", 401, "auth_required")
    if current_user.get("status") != "active":
        return _json_error("Account is disabled.", 403, "account_disabled")
    if not allow_incomplete and not current_user.get("profile_complete"):
        return _json_error("Complete your profile before using the app.", 409, "profile_incomplete")
    return None



def _require_admin():
    result = _require_user()
    if result:
        return result
    if g.get("current_user_row", {}).get("role") != "admin":
        return _json_error("Admin access required.", 403, "admin_required")
    return None



def _require_api_key_or_user():
    if g.get("current_user_row") or g.get("api_key_authenticated"):
        return None
    return _json_error("Authentication required.", 401, "auth_required")



def _serialize_thread(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "last_message_at": row["last_message_at"].isoformat() if row.get("last_message_at") else None,
        "archived_at": row["archived_at"].isoformat() if row.get("archived_at") else None,
        "deleted_at": row["deleted_at"].isoformat() if row.get("deleted_at") else None,
        "last_message_preview": row.get("last_message_preview"),
    }



def _serialize_message(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = json_loads(row.get("message_meta_json"), {})
    return {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "role": row["role"],
        "content": row["content"],
        "response_mode": row.get("response_mode"),
        "sources": json_loads(row.get("sources_json"), []),
        "model_name": row.get("model_name"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "log_id": meta.get("log_id"),
    }



def _fetch_thread(conn, user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT ct.*,
                   (
                       SELECT content FROM conversation_messages cm
                       WHERE cm.thread_id = ct.id
                       ORDER BY cm.created_at DESC,
                                CASE cm.role
                                    WHEN 'assistant' THEN 0
                                    WHEN 'user' THEN 1
                                    ELSE 2
                                END,
                                cm.id DESC
                       LIMIT 1
                   ) AS last_message_preview
            FROM conversation_threads ct
            WHERE ct.id = %s AND ct.user_id = %s AND ct.deleted_at IS NULL
            LIMIT 1
            """,
            (thread_id, user_id),
        )
        return cursor.fetchone()
    finally:
        cursor.close()



def _list_threads(conn, user_id: str) -> List[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT ct.*,
                   (
                       SELECT content FROM conversation_messages cm
                       WHERE cm.thread_id = ct.id
                       ORDER BY cm.created_at DESC,
                                CASE cm.role
                                    WHEN 'assistant' THEN 0
                                    WHEN 'user' THEN 1
                                    ELSE 2
                                END,
                                cm.id DESC
                       LIMIT 1
                   ) AS last_message_preview
            FROM conversation_threads ct
            WHERE ct.user_id = %s AND ct.deleted_at IS NULL
            ORDER BY CASE WHEN ct.archived_at IS NULL THEN 0 ELSE 1 END,
                     ct.last_message_at DESC,
                     ct.created_at DESC
            """,
            (user_id,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()



def _create_thread(conn, user_id: str, title: Optional[str]) -> Dict[str, Any]:
    thread_id = str(uuid.uuid4())
    final_title = title.strip() if title and title.strip() else "New conversation"
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO conversation_threads (id, user_id, title, thread_state_json, last_message_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, final_title, json_dumps(create_empty_cache()), utcnow()),
        )
    finally:
        cursor.close()
    return _fetch_thread(conn, user_id, thread_id)



def _update_thread(conn, thread_id: str, *, title: Optional[str] = None, archived: Optional[bool] = None) -> None:
    updates = []
    values: List[Any] = []
    if title is not None:
        updates.append("title = %s")
        values.append(title)
    if archived is not None:
        updates.append("archived_at = %s")
        values.append(utcnow() if archived else None)
    if not updates:
        return
    values.append(thread_id)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"UPDATE conversation_threads SET {', '.join(updates)} WHERE id = %s",
            tuple(values),
        )
    finally:
        cursor.close()



def _soft_delete_thread(conn, thread_id: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE conversation_threads SET deleted_at = %s WHERE id = %s",
            (utcnow(), thread_id),
        )
    finally:
        cursor.close()



def _fetch_messages(conn, thread_id: str, *, limit: int, before: Optional[str]) -> List[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        params: List[Any] = [thread_id]
        where_clause = "WHERE thread_id = %s"
        if before:
            cursor.execute(
                "SELECT created_at FROM conversation_messages WHERE id = %s AND thread_id = %s LIMIT 1",
                (before, thread_id),
            )
            pivot = cursor.fetchone()
            if pivot and pivot.get("created_at"):
                where_clause += " AND created_at < %s"
                params.append(pivot["created_at"])
        params.append(limit)
        cursor.execute(
            f"""
            SELECT *
            FROM conversation_messages
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        rows.reverse()
        return rows
    finally:
        cursor.close()



def _fetch_recent_history(conn, thread_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    return _fetch_messages(conn, thread_id, limit=limit, before=None)



def _insert_message(
    conn,
    *,
    thread_id: str,
    user_id: str,
    role: str,
    content: str,
    response_mode: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    model_name: Optional[str] = None,
    message_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    message_id = str(uuid.uuid4())
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO conversation_messages (
                id, thread_id, user_id, role, content, response_mode,
                sources_json, model_name, message_meta_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                thread_id,
                user_id,
                role,
                content,
                response_mode,
                json_dumps(sources) if sources is not None else None,
                model_name,
                json_dumps(message_meta) if message_meta is not None else None,
                utcnow(),
            ),
        )
    finally:
        cursor.close()
    return _fetch_messages(conn, thread_id, limit=1, before=None)[-1]



def _update_thread_state(conn, thread_id: str, thread_state: Dict[str, Any]) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE conversation_threads SET thread_state_json = %s, last_message_at = %s WHERE id = %s",
            (json_dumps(thread_state), utcnow(), thread_id),
        )
    finally:
        cursor.close()



def _update_message_meta(conn, message_id: str, message_meta: Dict[str, Any]) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE conversation_messages SET message_meta_json = %s WHERE id = %s",
            (json_dumps(message_meta), message_id),
        )
    finally:
        cursor.close()



def extract_sources(mode: str, result: Dict[str, Any]) -> List[Dict[str, str]]:
    sources: List[Dict[str, str]] = []

    if mode == "sql":
        sql_query = result.get("sql", "")
        if sql_query:
            match = re.search(r"FROM\s+`?(\w+)`?", sql_query, re.IGNORECASE)
            if match:
                sources.append({"type": "sql", "table": match.group(1)})

    elif mode == "rag":
        metadata = result.get("metadata", [])
        seen = set()
        for meta in metadata[:5]:
            source = meta.get("source", "Unknown")
            doc_type = meta.get("doc_type", "unknown")
            key = f"{source}:{doc_type}"
            print(key)
            if key in seen:
                continue
            seen.add(key)
            link = meta.get("link", "")
            base_dir = DOC_TYPE_DIRS.get(doc_type, "Data")
            if link:
                path = link
                source_label = source
            elif base_dir.startswith(("http://", "https://")):
                normalized_source = source.replace(" ", "-")
                if normalized_source.endswith(".txt"):
                    normalized_source = normalized_source[:-4] + ".html"
                path = urljoin(base_dir, normalized_source)
                source_label = source
            else:
                path = str(Path(base_dir) / source)
                source_label = source
            sources.append({
                "type": "rag",
                "source": source_label,
                "doc_type": doc_type,
                "path": path,
            })

    elif mode == "hybrid":
        sql_part = result.get("sql", {}) if isinstance(result.get("sql"), dict) else result.get("sql")
        rag_part = result.get("rag", {}) if isinstance(result.get("rag"), dict) else {}
        if isinstance(sql_part, dict):
            sql_query = sql_part.get("sql", "")
            if sql_query:
                match = re.search(r"FROM\s+`?(\w+)`?", sql_query, re.IGNORECASE)
                if match:
                    sources.append({"type": "sql", "table": match.group(1)})
        rag_metadata = rag_part.get("metadata", []) if isinstance(rag_part, dict) else []
        seen = set()
        for meta in rag_metadata[:3]:
            source = meta.get("source", "Unknown")
            doc_type = meta.get("doc_type", "unknown")
            key = f"{source}:{doc_type}"
            if key in seen:
                continue
            seen.add(key)
            link = meta.get("link", "")
            base_dir = DOC_TYPE_DIRS.get(doc_type, "Data")
            sources.append({
                "type": "rag",
                "source": source,
                "doc_type": doc_type,
                "path": link or str(Path(base_dir) / source),
            })

    return sources



def log_interaction(
    *,
    session_id: str,
    client_query: str,
    app_response: str,
    mode: str = "",
    log_id: Optional[int] = None,
    rating: str = "",
    flag_reason: str = "",
    flag_details: str = "",
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Optional[int]:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if log_id:
            update_fields = []
            values: List[Any] = []
            if rating:
                update_fields.append("client_response_rating = %s")
                values.append(rating)
            if flag_reason:
                update_fields.append("flagged = TRUE")
                update_fields.append("flag_reason = %s")
                update_fields.append("flag_details = %s")
                update_fields.append("flagged_at = NOW()")
                values.extend([flag_reason, flag_details])
            if app_response:
                update_fields.append("app_response = %s")
                values.append(app_response)
            if update_fields:
                values.append(log_id)
                cursor.execute(
                    f"UPDATE interaction_log SET {', '.join(update_fields)} WHERE id = %s",
                    tuple(values),
                )
            conn.commit()
            return log_id

        cursor.execute(
            """
            INSERT INTO interaction_log (
                session_id, app_version, client_query, app_response,
                data_selected, user_id, thread_id, message_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                Config.API_VERSION,
                client_query,
                app_response,
                mode,
                user_id,
                thread_id,
                message_id,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as exc:
        print(f"Error logging interaction: {exc}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



def _conversation_history_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    for row in rows:
        if row["role"] not in {"user", "assistant"}:
            continue
        history.append({"role": row["role"], "content": row["content"]})
    return history[-20:]



def _execute_agent_response(
    message: str,
    *,
    conversation_history: List[Dict[str, str]],
    retrieval_cache: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    cache = retrieval_cache or create_empty_cache()
    has_history = bool(conversation_history)
    has_cache = bool(cache and cache.get("mode"))

    if has_history or has_cache:
        history_check = _check_if_needs_new_data(message, conversation_history, cache)
    else:
        history_check = {"needs_new_data": True, "reason": "No history or cache"}

    if not history_check.get("needs_new_data", True) and (has_history or has_cache):
        answer = _answer_from_history(message, conversation_history, cache)
        return {
            "answer": answer,
            "mode": "history",
            "sources": [],
            "result": {"answer": answer},
            "retrieval_cache": cache,
        }

    plan = _route_question(message)
    mode = plan.get("mode", "hybrid")
    if mode == "sql":
        result = _run_sql(message, conversation_history)
        next_cache = build_retrieval_cache(
            mode="sql",
            question=message,
            answer=result.get("answer", ""),
            sql_result=result.get("result"),
            sql_query=result.get("sql"),
        )
    elif mode == "rag":
        result = _run_rag(message, plan, conversation_history)
        next_cache = build_retrieval_cache(
            mode="rag",
            question=message,
            answer=result.get("answer", ""),
            rag_chunks=result.get("chunks"),
            rag_metadata=result.get("metadata"),
        )
    else:
        result = _run_hybrid(message, plan, conversation_history)
        sql_part = result.get("sql", {}) if isinstance(result.get("sql"), dict) else {}
        rag_part = result.get("rag", {}) if isinstance(result.get("rag"), dict) else {}
        next_cache = build_retrieval_cache(
            mode="hybrid",
            question=message,
            answer=result.get("answer", ""),
            sql_result=sql_part.get("result"),
            sql_query=sql_part.get("sql"),
            rag_chunks=rag_part.get("chunks"),
            rag_metadata=rag_part.get("metadata"),
        )

    answer = result.get("answer", "I couldn't find an answer to your question.")
    sources = extract_sources(mode, result)
    return {
        "answer": answer,
        "mode": mode,
        "sources": sources,
        "result": result,
        "retrieval_cache": next_cache,
    }


# =============================================================================
# Request lifecycle
# =============================================================================
@app.before_request
def before_request_handler():
    if request.method == "OPTIONS":
        return ("", 204)

    g.api_key_authenticated = False
    g.current_user_row = None
    g.current_user = None
    g.linked_providers = []
    g.session_row = None
    g.session_id = None
    g.clear_auth_cookies = False
    g.csrf_cookie_written = False

    provided_api_key = request.headers.get("RethinkAI-API-Key", "")
    if provided_api_key and provided_api_key in Config.RETHINKAI_API_KEYS:
        g.api_key_authenticated = True
        if "session_id" not in session:
            session.permanent = True
            session["session_id"] = str(uuid.uuid4())
        g.session_id = session.get("session_id")

    session_token = request.cookies.get(Config.AUTH_SESSION_COOKIE_NAME, "")
    if not session_token:
        return None

    conn = None
    try:
        conn = get_db_connection()
        session_row = _current_session_row(conn, session_token)
        if not session_row:
            g.clear_auth_cookies = True
            return None
        if session_row.get("revoked_at") or session_row.get("expires_at") <= utcnow():
            _revoke_session(conn, session_row["session_id"])
            conn.commit()
            g.clear_auth_cookies = True
            return None

        providers = _provider_names(conn, session_row["user_id"])
        promoted = _promote_user_to_admin_if_configured(
            conn,
            user_id=session_row["user_id"],
            email=session_row["email"],
            current_role=session_row.get("role"),
            audit_event="admin_role_bootstrap",
        )
        _touch_session(conn, session_row["session_id"])
        conn.commit()
        if promoted:
            session_row = _current_session_row(conn, session_token) or session_row

        g.session_row = session_row
        g.current_user_row = session_row
        g.linked_providers = providers
        g.current_user = serialize_user(session_row, providers)
        g.session_id = session_row["session_id"]
    except Exception as exc:
        print(f"Warning: session lookup failed: {exc}")
    finally:
        if conn:
            conn.close()


@app.after_request
def after_request_handler(response):
    if getattr(g, "clear_auth_cookies", False):
        _clear_auth_cookies(response)
    if not request.cookies.get(Config.AUTH_CSRF_COOKIE_NAME) and not getattr(g, "csrf_cookie_written", False):
        response.set_cookie(
            Config.AUTH_CSRF_COOKIE_NAME,
            generate_token(24),
            **_cookie_kwargs(httponly=False),
        )
        g.csrf_cookie_written = True
    return response


# =============================================================================
# Auth endpoints
# =============================================================================
@app.route("/auth/me", methods=["GET"])
def auth_me():
    return jsonify(
        {
            "authenticated": bool(g.get("current_user")),
            "user": g.get("current_user"),
            "google_oauth_enabled": bool(oauth),
        }
    )


@app.route("/auth/signup", methods=["POST"])
def auth_signup():
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    email = normalize_email(payload.get("email", ""))
    username = normalize_username(payload.get("username", ""))
    password = payload.get("password", "")

    username_error = validate_username(username)
    if username_error:
        return _json_error(username_error, 400, "invalid_username")
    password_error = validate_password(password, username, email)
    if password_error:
        return _json_error(password_error, 400, "invalid_password")
    if not email or "@" not in email:
        return _json_error("A valid email address is required.", 400, "invalid_email")

    conn = None
    try:
        conn = get_db_connection()
        existing_user = _fetch_user_by_email(conn, email)
        if existing_user:
            return _json_error("An account with that email already exists.", 409, "email_exists")
        existing_username = _fetch_user_by_username(conn, username)
        if existing_username:
            return _json_error("That username is already taken.", 409, "username_exists")

        user = _create_user(conn, email, username, profile_complete=True)
        _promote_user_to_admin_if_configured(
            conn,
            user_id=user["id"],
            email=email,
            current_role=user.get("role"),
            audit_event="admin_role_bootstrap",
        )
        _create_auth_identity(
            conn,
            user_id=user["id"],
            provider="password",
            password_hash_value=hash_password(password),
        )
        _update_user_login_stamp(conn, user["id"])
        _update_identity_last_used(conn, user["id"], "password")
        session_info = _create_web_session(conn, user["id"])
        _record_auth_event(conn, "signup_password", success=True, user_id=user["id"], details={"email": email})
        conn.commit()

        providers = _provider_names(conn, user["id"])
        fresh_user = _fetch_user_by_id(conn, user["id"])
        response = jsonify({"user": serialize_user(fresh_user, providers)})
        _set_auth_cookies(response, session_info["session_token"], session_info["csrf_token"], session_info["expires_at"])
        return response, 201
    except RuntimeError as exc:
        if conn:
            conn.rollback()
        return _json_error(str(exc), 500, "dependency_missing")
    except mysql.connector.IntegrityError as exc:
        if conn:
            conn.rollback()
        return _json_error(f"Failed to create account: {exc}", 409, "signup_conflict")
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error in signup: {exc}")
        return _json_error("Failed to create account.", 500, "signup_failed")
    finally:
        if conn:
            conn.close()


@app.route("/auth/login", methods=["POST"])
def auth_login():
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    email = normalize_email(payload.get("email", ""))
    password = payload.get("password", "")
    ip_address = get_client_ip(request.headers, request.remote_addr)

    if not email or not password:
        return _json_error("Email and password are required.", 400, "missing_credentials")

    conn = None
    try:
        conn = get_db_connection()
        login_attempt = _fetch_login_attempt(conn, email, ip_address)
        if _is_locked(login_attempt):
            return _json_error("Too many failed login attempts. Try again later.", 429, "login_locked")

        login_row = _fetch_password_login_row(conn, email)
        if not login_row or login_row.get("status") != "active":
            locked_until = _record_failed_login(conn, email, ip_address)
            _record_auth_event(conn, "login_password", success=False, details={"email": email, "locked_until": locked_until.isoformat() if locked_until else None})
            conn.commit()
            return _json_error("Invalid email or password.", 401, "invalid_credentials")

        password_ok, replacement_hash = verify_password(login_row["password_hash"], password)
        if not password_ok:
            locked_until = _record_failed_login(conn, email, ip_address)
            _record_auth_event(conn, "login_password", success=False, user_id=login_row["id"], details={"email": email, "locked_until": locked_until.isoformat() if locked_until else None})
            conn.commit()
            return _json_error("Invalid email or password.", 401, "invalid_credentials")

        if replacement_hash:
            _update_password_hash(conn, login_row["identity_id"], replacement_hash)
        _promote_user_to_admin_if_configured(
            conn,
            user_id=login_row["id"],
            email=email,
            current_role=login_row.get("role"),
            audit_event="admin_role_bootstrap",
        )
        _clear_login_attempts(conn, email, ip_address)
        _update_user_login_stamp(conn, login_row["id"])
        _update_identity_last_used(conn, login_row["id"], "password")
        session_info = _create_web_session(conn, login_row["id"])
        _record_auth_event(conn, "login_password", success=True, user_id=login_row["id"], details={"email": email})
        conn.commit()

        providers = _provider_names(conn, login_row["id"])
        user_row = _fetch_user_by_id(conn, login_row["id"])
        response = jsonify({"user": serialize_user(user_row, providers)})
        _set_auth_cookies(response, session_info["session_token"], session_info["csrf_token"], session_info["expires_at"])
        return response
    except RuntimeError as exc:
        if conn:
            conn.rollback()
        return _json_error(str(exc), 500, "dependency_missing")
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error in login: {exc}")
        return _json_error("Failed to log in.", 500, "login_failed")
    finally:
        if conn:
            conn.close()


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    result = _require_user(allow_incomplete=True)
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    conn = None
    try:
        conn = get_db_connection()
        _revoke_session(conn, g.session_row["session_id"])
        _record_auth_event(conn, "logout", success=True, user_id=g.current_user_row["id"])
        conn.commit()
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error in logout: {exc}")
        return _json_error("Failed to log out.", 500, "logout_failed")
    finally:
        if conn:
            conn.close()

    response = jsonify({"ok": True})
    _clear_auth_cookies(response)
    return response


@app.route("/auth/google/start", methods=["GET"])
def auth_google_start():
    if not oauth:
        return _json_error("Google OAuth is not configured.", 503, "google_oauth_disabled")

    intent = request.args.get("intent", "login")
    next_path = request.args.get("next", "/")
    if not is_safe_next_path(next_path):
        next_path = "/"

    if intent not in {"login", "link"}:
        return _json_error("Invalid OAuth intent.", 400, "invalid_oauth_intent")

    if intent == "link":
        result = _require_user(allow_incomplete=True)
        if result:
            return result
        session["oauth_user_id"] = g.current_user_row["id"]
    else:
        session.pop("oauth_user_id", None)

    session["oauth_intent"] = intent
    session["oauth_next"] = next_path
    return oauth.google.authorize_redirect(Config.GOOGLE_REDIRECT_URI, prompt="select_account")


@app.route("/auth/google/callback", methods=["GET"])
def auth_google_callback():
    next_path = session.pop("oauth_next", "/")
    intent = session.pop("oauth_intent", "login")
    oauth_user_id = session.pop("oauth_user_id", None)

    if not oauth:
        return redirect(_build_oauth_redirect(next_path, "google_oauth_disabled"))

    conn = None
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.get("userinfo").json()

        email = normalize_email(userinfo.get("email", ""))
        subject = userinfo.get("sub")
        if not subject or not email or not userinfo.get("email_verified"):
            return redirect(_build_oauth_redirect(next_path, "google_email_not_verified"))

        conn = get_db_connection()
        google_user = _fetch_google_user_by_subject(conn, subject)
        existing_email_user = _fetch_user_by_email(conn, email)

        if intent == "link":
            result = _require_user(allow_incomplete=True)
            if result:
                return redirect(_build_oauth_redirect(next_path, "login_required_for_link"))
            if oauth_user_id != g.current_user_row["id"]:
                return redirect(_build_oauth_redirect(next_path, "oauth_link_session_mismatch"))
            if email != g.current_user_row["email"]:
                return redirect(_build_oauth_redirect(next_path, "google_email_mismatch"))
            if google_user and google_user["id"] != g.current_user_row["id"]:
                return redirect(_build_oauth_redirect(next_path, "google_account_already_linked"))
            if not google_user:
                _create_auth_identity(conn, user_id=g.current_user_row["id"], provider="google", provider_subject=subject)
                _record_auth_event(conn, "google_link", success=True, user_id=g.current_user_row["id"], details={"email": email})
                session_info = _create_web_session(conn, g.current_user_row["id"])
                _revoke_session(conn, g.session_row["session_id"])
                conn.commit()
                response = redirect(_build_oauth_redirect(next_path))
                _set_auth_cookies(response, session_info["session_token"], session_info["csrf_token"], session_info["expires_at"])
                return response

            response = redirect(_build_oauth_redirect(next_path))
            return response

        if google_user:
            _promote_user_to_admin_if_configured(
                conn,
                user_id=google_user["id"],
                email=email,
                current_role=google_user.get("role"),
                audit_event="admin_role_bootstrap",
            )
            _update_user_login_stamp(conn, google_user["id"])
            _update_identity_last_used(conn, google_user["id"], "google")
            session_info = _create_web_session(conn, google_user["id"])
            _record_auth_event(conn, "login_google", success=True, user_id=google_user["id"], details={"email": email})
            conn.commit()
            response = redirect(_build_oauth_redirect(next_path))
            _set_auth_cookies(response, session_info["session_token"], session_info["csrf_token"], session_info["expires_at"])
            return response

        if existing_email_user:
            _record_auth_event(conn, "login_google", success=False, user_id=existing_email_user["id"], details={"email": email, "reason": "existing_unlinked_account"})
            conn.commit()
            return redirect(_build_oauth_redirect(next_path, "existing_account_requires_password_login"))

        temp_username = f"user-{uuid.uuid4().hex[:8]}"
        user_row = _create_user(conn, email, temp_username, profile_complete=False)
        _promote_user_to_admin_if_configured(
            conn,
            user_id=user_row["id"],
            email=email,
            current_role=user_row.get("role"),
            audit_event="admin_role_bootstrap",
        )
        _create_auth_identity(conn, user_id=user_row["id"], provider="google", provider_subject=subject)
        _update_user_login_stamp(conn, user_row["id"])
        _update_identity_last_used(conn, user_row["id"], "google")
        session_info = _create_web_session(conn, user_row["id"])
        _record_auth_event(conn, "signup_google", success=True, user_id=user_row["id"], details={"email": email})
        conn.commit()

        response = redirect(_build_oauth_redirect(next_path))
        _set_auth_cookies(response, session_info["session_token"], session_info["csrf_token"], session_info["expires_at"])
        return response
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Google OAuth callback failed: {exc}")
        return redirect(_build_oauth_redirect(next_path, "google_oauth_failed"))
    finally:
        if conn:
            conn.close()


@app.route("/auth/complete-profile", methods=["POST"])
def auth_complete_profile():
    result = _require_user(allow_incomplete=True)
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    username = normalize_username(payload.get("username", ""))
    username_error = validate_username(username)
    if username_error:
        return _json_error(username_error, 400, "invalid_username")

    conn = None
    try:
        conn = get_db_connection()
        existing = _fetch_user_by_username(conn, username)
        if existing and existing["id"] != g.current_user_row["id"]:
            return _json_error("That username is already taken.", 409, "username_exists")

        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET username = %s, profile_complete = TRUE WHERE id = %s",
                (username, g.current_user_row["id"]),
            )
        finally:
            cursor.close()
        _record_auth_event(conn, "complete_profile", success=True, user_id=g.current_user_row["id"], details={"username": username})
        conn.commit()

        user_row = _fetch_user_by_id(conn, g.current_user_row["id"])
        providers = _provider_names(conn, g.current_user_row["id"])
        return jsonify({"user": serialize_user(user_row, providers)})
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error completing profile: {exc}")
        return _json_error("Failed to complete profile.", 500, "profile_update_failed")
    finally:
        if conn:
            conn.close()


@app.route("/auth/unlink/google", methods=["POST"])
def auth_unlink_google():
    result = _require_user()
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    conn = None
    try:
        conn = get_db_connection()
        google_identity = _fetch_identity_for_user(conn, g.current_user_row["id"], "google")
        if not google_identity:
            return _json_error("Google is not linked to this account.", 400, "google_not_linked")
        password_identity = _fetch_identity_for_user(conn, g.current_user_row["id"], "password")
        if not password_identity:
            return _json_error("You cannot remove your last login method.", 400, "last_login_method")

        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM auth_identities WHERE id = %s", (google_identity["id"],))
        finally:
            cursor.close()
        _record_auth_event(conn, "google_unlink", success=True, user_id=g.current_user_row["id"])
        conn.commit()

        user_row = _fetch_user_by_id(conn, g.current_user_row["id"])
        providers = _provider_names(conn, g.current_user_row["id"])
        return jsonify({"user": serialize_user(user_row, providers)})
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error unlinking Google: {exc}")
        return _json_error("Failed to unlink Google.", 500, "google_unlink_failed")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Conversation endpoints
# =============================================================================
@app.route("/conversations", methods=["GET"])
def list_conversations():
    result = _require_user()
    if result:
        return result

    conn = None
    try:
        conn = get_db_connection()
        rows = _list_threads(conn, g.current_user_row["id"])
        return jsonify({"threads": [_serialize_thread(row) for row in rows]})
    except Exception as exc:
        print(f"Error listing conversations: {exc}")
        return _json_error("Failed to load conversations.", 500, "conversation_list_failed")
    finally:
        if conn:
            conn.close()


@app.route("/conversations", methods=["POST"])
def create_conversation():
    result = _require_user()
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    title = payload.get("title")

    conn = None
    try:
        conn = get_db_connection()
        thread = _create_thread(conn, g.current_user_row["id"], title)
        conn.commit()
        return jsonify({"thread": _serialize_thread(thread)}), 201
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error creating conversation: {exc}")
        return _json_error("Failed to create conversation.", 500, "conversation_create_failed")
    finally:
        if conn:
            conn.close()


@app.route("/conversations/<thread_id>", methods=["PATCH"])
def update_conversation(thread_id: str):
    result = _require_user()
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    title = payload.get("title")
    archived = payload.get("archived") if "archived" in payload else None

    conn = None
    try:
        conn = get_db_connection()
        thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        if not thread:
            return _json_error("Conversation not found.", 404, "conversation_not_found")
        final_title = None
        if title is not None:
            final_title = title.strip()
            if not final_title:
                return _json_error("Title cannot be empty.", 400, "invalid_title")
        _update_thread(conn, thread_id, title=final_title, archived=bool(archived) if archived is not None else None)
        conn.commit()
        refreshed = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        return jsonify({"thread": _serialize_thread(refreshed)})
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error updating conversation: {exc}")
        return _json_error("Failed to update conversation.", 500, "conversation_update_failed")
    finally:
        if conn:
            conn.close()


@app.route("/conversations/<thread_id>", methods=["DELETE"])
def delete_conversation(thread_id: str):
    result = _require_user()
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    conn = None
    try:
        conn = get_db_connection()
        thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        if not thread:
            return _json_error("Conversation not found.", 404, "conversation_not_found")
        _soft_delete_thread(conn, thread_id)
        conn.commit()
        return jsonify({"ok": True})
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error deleting conversation: {exc}")
        return _json_error("Failed to delete conversation.", 500, "conversation_delete_failed")
    finally:
        if conn:
            conn.close()


@app.route("/conversations/<thread_id>/messages", methods=["GET"])
def get_conversation_messages(thread_id: str):
    result = _require_user()
    if result:
        return result

    limit = max(1, min(request.args.get("limit", 50, type=int), 100))
    before = request.args.get("before")

    conn = None
    try:
        conn = get_db_connection()
        thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        if not thread:
            return _json_error("Conversation not found.", 404, "conversation_not_found")
        messages = _fetch_messages(conn, thread_id, limit=limit, before=before)
        return jsonify({
            "thread": _serialize_thread(thread),
            "messages": [_serialize_message(row) for row in messages],
        })
    except Exception as exc:
        print(f"Error fetching messages: {exc}")
        return _json_error("Failed to load messages.", 500, "conversation_messages_failed")
    finally:
        if conn:
            conn.close()


@app.route("/conversations/<thread_id>/messages", methods=["POST"])
def post_conversation_message(thread_id: str):
    result = _require_user()
    if result:
        return result
    csrf_error = _enforce_csrf()
    if csrf_error:
        return csrf_error

    payload = request.get_json() or {}
    message = (payload.get("message") or "").strip()
    if not message:
        return _json_error("Message is required.", 400, "missing_message")

    conn = None
    try:
        conn = get_db_connection()
        thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        if not thread:
            return _json_error("Conversation not found.", 404, "conversation_not_found")

        history_rows = _fetch_recent_history(conn, thread_id, limit=20)
        conversation_history = _conversation_history_from_rows(history_rows)
        thread_state = json_loads(thread.get("thread_state_json"), create_empty_cache())
        conn.close()
        conn = None

        # Run the expensive agent path outside any open DB transaction so
        # long LLM/sql execution does not hold row locks on the conversation.
        agent_result = _execute_agent_response(
            message,
            conversation_history=conversation_history,
            retrieval_cache=thread_state,
        )
        answer = agent_result["answer"]
        mode = agent_result["mode"]
        sources = agent_result["sources"]
        next_cache = agent_result["retrieval_cache"]

        conn = get_db_connection()
        thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        if not thread:
            return _json_error("Conversation not found.", 404, "conversation_not_found")

        user_message_row = _insert_message(
            conn,
            thread_id=thread_id,
            user_id=g.current_user_row["id"],
            role="user",
            content=message,
        )

        assistant_message_row = _insert_message(
            conn,
            thread_id=thread_id,
            user_id=g.current_user_row["id"],
            role="assistant",
            content=answer,
            response_mode=mode,
            sources=sources,
            model_name=os.getenv("GEMINI_MODEL", ""),
        )

        if thread["title"] == "New conversation" and len(history_rows) == 0:
            _update_thread(conn, thread_id, title=summarize_thread_title(message))
        _update_thread_state(conn, thread_id, next_cache)

        log_id = log_interaction(
            session_id=g.session_row["session_id"],
            client_query=message,
            app_response=answer,
            mode=mode,
            user_id=g.current_user_row["id"],
            thread_id=thread_id,
            message_id=assistant_message_row["id"],
        )
        _update_message_meta(conn, assistant_message_row["id"], {"log_id": log_id})
        conn.commit()

        refreshed_thread = _fetch_thread(conn, g.current_user_row["id"], thread_id)
        assistant_message_row["message_meta_json"] = json_dumps({"log_id": log_id})

        return jsonify(
            {
                "thread": _serialize_thread(refreshed_thread),
                "user_message": _serialize_message(user_message_row),
                "assistant_message": _serialize_message(assistant_message_row),
            }
        ), 201
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"Error posting conversation message: {exc}")
        return _json_error("Failed to send message.", 500, "conversation_message_failed")
    finally:
        if conn:
            conn.close()


# =============================================================================
# Legacy compatibility endpoints
# =============================================================================
@app.route("/chat", methods=["POST"])
def chat():
    result = _require_api_key_or_user()
    if result:
        return result

    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    conversation_history = data.get("conversation_history", [])
    if not message:
        return _json_error("Message is required.", 400, "missing_message")

    session_id = g.get("session_id") or str(uuid.uuid4())
    if g.get("api_key_authenticated") and "session_id" not in session:
        session.permanent = True
        session["session_id"] = session_id
    elif g.get("api_key_authenticated"):
        session_id = session.get("session_id")

    _cleanup_old_legacy_caches()
    retrieval_cache = _legacy_session_caches.get(session_id, create_empty_cache())

    try:
        agent_result = _execute_agent_response(
            message,
            conversation_history=conversation_history,
            retrieval_cache=retrieval_cache,
        )
        _legacy_session_caches[session_id] = agent_result["retrieval_cache"]
        log_id = log_interaction(
            session_id=session_id,
            client_query=message,
            app_response=agent_result["answer"],
            mode=agent_result["mode"],
            user_id=g.current_user_row["id"] if g.get("current_user_row") else None,
        )
        return jsonify(
            {
                "session_id": session_id,
                "response": agent_result["answer"],
                "sources": agent_result["sources"],
                "mode": agent_result["mode"],
                "log_id": log_id,
            }
        )
    except Exception as exc:
        print(f"Error in /chat: {exc}")
        return _json_error("Internal server error.", 500, "chat_failed")


@app.route("/log", methods=["POST", "PUT"])
def log_endpoint():
    result = _require_api_key_or_user()
    if result:
        return result
    if request.method in {"POST", "PUT"} and g.get("current_user_row"):
        csrf_error = _enforce_csrf()
        if csrf_error:
            return csrf_error

    data = request.get_json() or {}
    session_id = g.get("session_id") or (g.session_row["session_id"] if g.get("session_row") else str(uuid.uuid4()))

    if request.method == "POST":
        client_query = data.get("client_query", "")
        app_response = data.get("app_response", "")
        mode = data.get("mode", "")
        if not client_query:
            return _json_error("client_query is required", 400, "missing_client_query")
        log_id = log_interaction(
            session_id=session_id,
            client_query=client_query,
            app_response=app_response,
            mode=mode,
            user_id=g.current_user_row["id"] if g.get("current_user_row") else None,
            thread_id=data.get("thread_id"),
            message_id=data.get("message_id"),
        )
        if not log_id:
            return _json_error("Failed to create log entry", 500, "log_create_failed")
        return jsonify({"log_id": log_id, "message": "Log entry created"}), 201

    log_id = data.get("log_id")
    if not log_id:
        return _json_error("log_id is required", 400, "missing_log_id")
    updated_id = log_interaction(
        session_id=session_id,
        client_query="",
        app_response="",
        log_id=log_id,
        rating=data.get("client_response_rating", ""),
        flag_reason=data.get("flag_reason", ""),
        flag_details=data.get("flag_details", ""),
        user_id=g.current_user_row["id"] if g.get("current_user_row") else None,
    )
    if not updated_id:
        return _json_error("Failed to update log entry", 500, "log_update_failed")
    return jsonify({"log_id": updated_id, "message": "Log entry updated"})


@app.route("/events", methods=["GET"])
def events():
    result = _require_api_key_or_user()
    if result:
        return result

    limit = max(1, min(request.args.get("limit", 10, type=int), 100))
    days_ahead = max(1, min(request.args.get("days_ahead", 7, type=int), 30))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, event_name, event_date, start_date, end_date,
                   start_time, end_time, raw_text, source_pdf
            FROM weekly_events
            WHERE start_date >= CURDATE()
              AND start_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)
            ORDER BY start_date ASC, start_time ASC
            LIMIT %s
            """,
            (days_ahead, limit),
        )
        rows = cursor.fetchall()
        events_list = []
        for row in rows:
            events_list.append(
                {
                    "id": row["id"],
                    "event_name": row["event_name"],
                    "event_date": row["event_date"],
                    "start_date": str(row["start_date"]) if row["start_date"] else None,
                    "end_date": str(row["end_date"]) if row["end_date"] else None,
                    "start_time": str(row["start_time"]) if row["start_time"] else None,
                    "end_time": str(row["end_time"]) if row["end_time"] else None,
                    "description": row["raw_text"],
                    "source": row["source_pdf"],
                }
            )
        return jsonify({"events": events_list, "total": len(events_list)})
    except Exception as exc:
        print(f"Error in /events: {exc}")
        return _json_error("Failed to fetch events.", 500, "events_failed")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/health", methods=["GET"])
def health():
    status = {
        "status": "ok",
        "version": Config.API_VERSION,
        "google_oauth_enabled": bool(oauth),
    }
    try:
        conn = get_db_connection()
        conn.close()
        status["database"] = "connected"
    except Exception:
        status["database"] = "disconnected"
        status["status"] = "degraded"
    return jsonify(status)


# =============================================================================
# Admin endpoints
# =============================================================================
@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    result = _require_admin()
    if result:
        return result

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS cnt FROM interaction_log")
        total = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM interaction_log WHERE flagged = TRUE")
        total_flagged = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM interaction_log
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            """
        )
        this_week = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt FROM interaction_log
            WHERE app_response LIKE %s
               OR app_response LIKE %s
               OR app_response LIKE %s
            """,
            ("%No results found%", "%couldn't find%", "%no data%"),
        )
        no_results = cursor.fetchone()["cnt"]

        cursor.execute(
            """
            SELECT data_selected AS mode, COUNT(*) AS cnt
            FROM interaction_log
            WHERE data_selected IS NOT NULL AND data_selected != ''
            GROUP BY data_selected
            ORDER BY cnt DESC
            """
        )
        mode_breakdown = {row["mode"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT flag_reason, COUNT(*) AS cnt
            FROM interaction_log
            WHERE flagged = TRUE AND flag_reason IS NOT NULL
            GROUP BY flag_reason
            ORDER BY cnt DESC
            """
        )
        flag_reasons = {row["flag_reason"]: row["cnt"] for row in cursor.fetchall()}

        return jsonify(
            {
                "total_interactions": total,
                "total_flagged": total_flagged,
                "interactions_this_week": this_week,
                "no_result_count": no_results,
                "mode_breakdown": mode_breakdown,
                "flag_reasons": flag_reasons,
            }
        )
    except Exception as exc:
        return _json_error(str(exc), 500, "admin_stats_failed")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/admin/flags", methods=["GET"])
def admin_flags():
    result = _require_admin()
    if result:
        return result

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, session_id, user_id, thread_id, client_query, app_response,
                   data_selected, flag_reason, flag_details, flagged_at, created_at
            FROM interaction_log
            WHERE flagged = TRUE
            ORDER BY flagged_at DESC
            LIMIT 200
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            for key in ("flagged_at", "created_at"):
                if row.get(key) and hasattr(row[key], "isoformat"):
                    row[key] = row[key].isoformat()
        return jsonify({"flags": rows})
    except Exception as exc:
        return _json_error(str(exc), 500, "admin_flags_failed")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/admin/interactions", methods=["GET"])
def admin_interactions():
    result = _require_admin()
    if result:
        return result

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, session_id, user_id, thread_id, client_query, app_response,
                   data_selected, flagged, created_at
            FROM interaction_log
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            if row.get("app_response") and len(row["app_response"]) > 200:
                row["app_response"] = row["app_response"][:200] + "..."
        return jsonify({"interactions": rows})
    except Exception as exc:
        return _json_error(str(exc), 500, "admin_interactions_failed")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/admin/no-results", methods=["GET"])
def admin_no_results():
    result = _require_admin()
    if result:
        return result

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, user_id, thread_id, client_query, data_selected, created_at
            FROM interaction_log
            WHERE app_response LIKE %s
               OR app_response LIKE %s
               OR app_response LIKE %s
               OR app_response LIKE %s
            ORDER BY created_at DESC
            LIMIT 100
            """,
            ("%No results found%", "%couldn't find%", "%no data%", "%I couldn't find%"),
        )
        rows = cursor.fetchall()
        for row in rows:
            if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
        return jsonify({"no_results": rows})
    except Exception as exc:
        return _json_error(str(exc), 500, "admin_no_results_failed")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    print(f"\n🚀 Agent API {Config.API_VERSION}")
    print(f"   Host: {Config.HOST}:{Config.PORT}")
    print(f"   Auth Modes: user sessions{' + API keys' if Config.RETHINKAI_API_KEYS else ''}")
    print(f"   Google OAuth: {'Enabled' if oauth else 'Disabled'}")
    print()
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
