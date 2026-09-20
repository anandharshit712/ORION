"""
Rate limiting for the ORION API (Phase 0.3, defect D-03).

A single module-level ``Limiter`` is shared by every route. Routes opt in with
``@limiter.limit(...)``; everything else inherits ``rate_limit_default``.

Why a shared limiter and not per-router ones: slowapi resolves limits through
``request.app.state.limiter``, so a second instance would silently not be
consulted. Import this one.

Limits and storage come from ``get_config().api`` — never hardcode them at a
call site. See ``config/default.yaml`` (``api:``) and the ``ORION_RATE_LIMIT_*``
environment variables.
"""

from __future__ import annotations

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from arep.config import get_config
from arep.utils.logging_config import get_logger

logger = get_logger("api.ratelimit")


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    ``X-Forwarded-For`` is only honoured when ``api.trust_proxy_headers`` is on,
    because a client talking to the API directly can put anything in that header
    and mint itself a fresh rate-limit bucket on every request. Behind a proxy
    the leftmost entry is the original client; entries after it are the proxy
    chain.
    """
    if get_config().api.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def principal_key(request: Request) -> str:
    """Rate-limit bucket for a request.

    Three tiers, most specific first:

    1. ``request.state.org_id`` — set by ``OrgAuthMiddleware``. One tenant
       hammering the API then cannot exhaust another tenant's budget by sharing
       an IP (both behind the same corporate NAT, say).
    2. A hash of the ``Authorization`` credential. The global default limit is
       enforced by ``SlowAPIMiddleware``, which runs *before* ``OrgAuthMiddleware``
       and so sees no ``request.state``; worse, a request bearing an invalid
       token is rejected by that middleware and would never reach a limiter
       keyed on state at all. Bucketing on the credential itself covers the
       flood-with-garbage-tokens case too. The raw credential is never used as
       a key — it would end up in limiter storage and in log lines.
    3. Client IP — all an unauthenticated caller (login, signup) has.
    """
    org_id = getattr(request.state, "org_id", None)
    if org_id:
        user_id = getattr(request.state, "user_id", None)
        return f"org:{org_id}:user:{user_id}"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        credential = auth_header[7:].strip()
        if credential:
            digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()[:32]
            return f"cred:{digest}"

    return f"ip:{client_ip(request)}"


# Limit strings are resolved per request rather than captured at import time:
# slowapi accepts a zero-arg callable, and a test (or an ops env-var change and
# reload_config()) then takes effect without re-importing the route module.

def login_limit() -> str:
    """Per-IP limit on POST /api/auth/login — the credential-stuffing control."""
    return get_config().api.rate_limit_login


def signup_limit() -> str:
    """Per-IP limit on POST /api/auth/signup and its /register alias."""
    return get_config().api.rate_limit_signup


def _default_limits() -> list[str]:
    cfg = get_config().api
    if not cfg.rate_limit_enabled or not cfg.rate_limit_default:
        return []
    return [cfg.rate_limit_default]


_cfg = get_config().api

limiter = Limiter(
    key_func=principal_key,
    default_limits=_default_limits(),
    storage_uri=_cfg.rate_limit_storage_uri,
    enabled=_cfg.rate_limit_enabled,
    headers_enabled=True,   # X-RateLimit-* on responses, so clients can back off
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 in the platform's error shape: {"detail": "..."}.

    slowapi's built-in handler returns {"error": ...}, which would make this the
    only endpoint family in the API with a different error body.
    """
    logger.warning(
        "Rate limit hit: %s %s by %s (limit %s)",
        request.method, request.url.path, principal_key(request), exc.detail,
    )
    response = JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )
    # Let the client know when to retry; slowapi fills the rest of the headers.
    request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)
    return response
