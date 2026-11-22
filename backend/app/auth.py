"""Authentication: PBKDF2 password hashing + HttpOnly session cookies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request, WebSocket

from .config import settings
from .db import db

COOKIE_NAME = "cctv_session"
_ITER = 310_000
_login_attempts: dict[str, list[float]] = {}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


def has_users() -> bool:
    return db.one("SELECT COUNT(*) AS c FROM users")["c"] > 0


def create_user(username: str, password: str) -> int:
    validate_password(password)
    return db.insert("users", {"username": username.strip(), "password_hash": hash_password(password), "created_at": time.time()})


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")


def check_rate_limit(ip: str):
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < 300]
    _login_attempts[ip] = attempts
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many login attempts. Try again in 5 minutes.")


def record_failed(ip: str):
    _login_attempts.setdefault(ip, []).append(time.time())


def authenticate(username: str, password: str) -> dict | None:
    u = db.one("SELECT * FROM users WHERE username=?", (username.strip(),))
    if u and verify_password(password, u["password_hash"]):
        return u
    return None


def create_session(user_id: int) -> str:
    db.cleanup_sessions()
    token = secrets.token_urlsafe(32)
    hours = settings.get("server.session_hours", 72)
    db.insert("sessions", {"token": token, "user_id": user_id, "created_at": time.time(), "expires_at": time.time() + hours * 3600})
    return token


def delete_session(token: str):
    db.execute("DELETE FROM sessions WHERE token=?", (token,))


def _user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    row = db.one(
        "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?",
        (token, time.time()),
    )
    return row


def require_user(request: Request) -> dict:
    user = _user_for_token(request.cookies.get(COOKIE_NAME))
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def ws_user(ws: WebSocket) -> dict | None:
    return _user_for_token(ws.cookies.get(COOKIE_NAME))
