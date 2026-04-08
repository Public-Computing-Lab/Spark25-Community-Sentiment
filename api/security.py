from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
except ImportError:  # pragma: no cover - dependency is enforced via requirements
    PasswordHasher = None
    InvalidHashError = ValueError
    VerifyMismatchError = ValueError


PASSWORD_MIN_LENGTH = 12
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_COMMON_WEAK_PASSWORDS = {
    "password",
    "password123",
    "123456789",
    "1234567890",
    "qwerty123",
    "letmein123",
    "admin123456",
    "welcome123",
}
_PASSWORD_HASHER = PasswordHasher() if PasswordHasher else None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_username(username: str) -> str:
    return (username or "").strip()


def validate_username(username: str) -> str | None:
    normalized = normalize_username(username)
    if not normalized:
        return "Username is required."
    if not _USERNAME_RE.match(normalized):
        return "Username must be 3-32 characters and only use letters, numbers, dots, dashes, or underscores."
    return None


def validate_password(password: str, username: str, email: str) -> str | None:
    pwd = password or ""
    if len(pwd) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."

    lowered = pwd.lower()
    username_lower = normalize_username(username).lower()
    email_lower = normalize_email(email)
    email_local = email_lower.split("@", 1)[0] if "@" in email_lower else email_lower

    if lowered in _COMMON_WEAK_PASSWORDS:
        return "Password is too common. Choose a less predictable password."
    if username_lower and username_lower in lowered:
        return "Password cannot contain your username."
    if email_local and email_local in lowered:
        return "Password cannot contain your email name."
    return None


def hash_password(password: str) -> str:
    if _PASSWORD_HASHER is None:
        raise RuntimeError("argon2-cffi is required for password hashing.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> tuple[bool, str | None]:
    if _PASSWORD_HASHER is None:
        raise RuntimeError("argon2-cffi is required for password verification.")
    try:
        valid = _PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False, None

    replacement_hash = None
    if valid and _PASSWORD_HASHER.check_needs_rehash(password_hash):
        replacement_hash = _PASSWORD_HASHER.hash(password)
    return True, replacement_hash


def generate_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)


def hash_token(token: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def is_safe_next_path(candidate: str | None) -> bool:
    if not candidate:
        return False
    return candidate.startswith("/") and not candidate.startswith("//")


def serialize_user(row: dict[str, Any] | None, linked_providers: Iterable[str] | None = None) -> dict[str, Any] | None:
    if not row:
        return None
    providers = sorted(set(linked_providers or []))
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"],
        "role": row["role"],
        "status": row["status"],
        "profile_complete": bool(row.get("profile_complete", False)),
        "linked_providers": providers,
        "has_password": "password" in providers,
        "has_google": "google" in providers,
        "last_login_at": row.get("last_login_at").isoformat() if row.get("last_login_at") else None,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }


def summarize_thread_title(message: str, max_len: int = 80) -> str:
    cleaned = " ".join((message or "").strip().split())
    if not cleaned:
        return "New conversation"
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def get_client_ip(headers: dict[str, Any], remote_addr: str | None) -> str:
    forwarded_for = headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return remote_addr or "unknown"


def json_dumps(value: Any) -> str:
    import json

    def _json_default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        return str(obj)

    return json.dumps(value, ensure_ascii=False, default=_json_default)


def json_loads(value: Any, default: Any) -> Any:
    import json

    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def get_token_secret() -> str:
    return os.getenv("TOKEN_PEPPER") or os.getenv("FLASK_SECRET_KEY", "agent-api-secret-2025")
