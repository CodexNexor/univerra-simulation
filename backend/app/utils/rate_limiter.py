"""
Small in-process rate limiter for API endpoints.

This is intentionally dependency-free so local deployments get protection even
before a production gateway is added.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Deque, Dict, Optional, Tuple

from flask import jsonify, request


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0
    remaining: int = 0


class InMemoryRateLimiter:
    """Sliding-window limiter keyed by endpoint/user/IP."""

    def __init__(self):
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.time()
        cutoff = now - max(window_seconds, 1)
        bucket = self._hits[key]

        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = int(max(1, window_seconds - (now - bucket[0])))
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=retry_after,
                remaining=0,
            )

        bucket.append(now)
        return RateLimitResult(
            allowed=True,
            retry_after_seconds=0,
            remaining=max(0, limit - len(bucket)),
        )


limiter = InMemoryRateLimiter()


def get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def rate_limit_key(scope: str, identity: Optional[str] = None) -> str:
    return f"{scope}:{identity or get_client_ip()}"


def rate_limit_response(retry_after_seconds: int):
    response = jsonify({
        "success": False,
        "error": "Too many requests. Please wait before trying again.",
        "retry_after_seconds": retry_after_seconds,
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after_seconds)
    return response


def check_rate_limit(scope: str, identity: Optional[str], limit: int, window_seconds: int) -> Optional[Tuple[object, int]]:
    result = limiter.check(rate_limit_key(scope, identity), limit, window_seconds)
    if result.allowed:
        return None
    return rate_limit_response(result.retry_after_seconds), 429


def rate_limited(
    scope: str,
    limit: int,
    window_seconds: int,
    identity_getter: Optional[Callable[[], str]] = None,
):
    """Decorator form for simple endpoints."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            identity = identity_getter() if identity_getter else None
            blocked = check_rate_limit(scope, identity, limit, window_seconds)
            if blocked:
                return blocked
            return func(*args, **kwargs)

        return wrapper

    return decorator
