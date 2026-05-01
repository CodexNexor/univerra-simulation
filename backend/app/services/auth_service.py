"""
Token helpers and Flask decorators for user authentication.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Dict, Optional

from flask import jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import Config
from .user_store import UserStore, UserStoreUnavailable


AUTH_SALT = "univerra-auth-token-v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(Config.AUTH_SECRET_KEY, salt=AUTH_SALT)


def create_auth_token(user: Dict[str, Any]) -> str:
    return _serializer().dumps({
        "user_id": user["user_id"],
        "email": user.get("email"),
    })


def decode_auth_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        return _serializer().loads(token, max_age=Config.AUTH_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None


def get_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return ""


def get_optional_user() -> Optional[Dict[str, Any]]:
    payload = decode_auth_token(get_bearer_token())
    if not payload:
        return None
    try:
        return UserStore.get_user(payload.get("user_id", ""))
    except UserStoreUnavailable:
        return None


def auth_error(message: str = "Authentication required", status: int = 401):
    return jsonify({"success": False, "error": message}), status


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        payload = decode_auth_token(get_bearer_token())
        if not payload:
            return auth_error()

        try:
            user = UserStore.get_user(payload.get("user_id", ""))
        except UserStoreUnavailable as exc:
            return auth_error(str(exc), 503)

        if not user:
            return auth_error("Session expired. Please log in again.", 401)

        request.current_user = user
        return func(*args, **kwargs)

    return wrapper


def current_user_id() -> Optional[str]:
    user = getattr(request, "current_user", None) or get_optional_user()
    return user.get("user_id") if user else None
