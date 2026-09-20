"""
ORION API Middleware.

Org-scoped authentication middleware.
Resolves both JWT tokens and API keys to (org_id, user_id, role)
and attaches them to the request state for downstream route handlers.

Every protected route reads from request.state.org_id — it never
inspects the token itself.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import Request, HTTPException
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from arep.api.auth import (
    CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, decode_access_token,
)
from arep.database.connection import get_session
from arep.database.models import UserRecord
from arep.database.repository import ApiKeyRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.middleware")

API_KEY_PREFIX = "sk-orion-"

# Routes that do NOT require authentication
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/register",
    "/api/auth/me",  # uses JWT dep directly — handled by route
    "/api/auth/logout",          # clearing cookies you may not have is a no-op
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
    "/api/auth/resend-verification",
}

# Path prefixes that bypass middleware (WebSocket auth handled separately)
PUBLIC_PREFIXES = (
    "/ws/",
)

# Methods that do not change state, and so need no CSRF token (RFC 9110).
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def hash_api_key(plaintext: str) -> str:
    """SHA256 hash of an API key. Fast, deterministic, suitable for indexed lookup."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Generate a fresh API key.

    Returns:
        (plaintext, key_hash, key_prefix) — plaintext returned to the user once,
        only key_hash + key_prefix stored.
    """
    raw = secrets.token_urlsafe(32)
    plaintext = f"{API_KEY_PREFIX}{raw}"
    return plaintext, hash_api_key(plaintext), plaintext[: len(API_KEY_PREFIX) + 8]


class OrgAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that resolves auth credentials on every request.

    Resolution order:
      1. Authorization: Bearer <api_key>  (starts with "sk-orion-")  → hash lookup
      2. Authorization: Bearer <jwt>      → decode JWT, extract org_id + role
      3. Public path  → skip auth entirely

    On success, sets:
      request.state.org_id  : str
      request.state.user_id : int
      request.state.role    : str  ("owner" | "admin" | "member" | "viewer")

    On failure (token present but invalid), returns 401.
    On no token + non-public path, sets state to None and lets route deps decide.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip preflight + public paths/prefixes
        if (
            request.method == "OPTIONS"
            or path in PUBLIC_PATHS
            or any(path.startswith(p) for p in PUBLIC_PREFIXES)
        ):
            request.state.org_id = None
            request.state.user_id = None
            request.state.role = None
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token = self._extract_token(auth_header)

        # Cookie fallback for the browser app (Phase 0.4, D-04). The header wins:
        # an SDK client that sends one is explicit about which identity it wants,
        # and a stale cookie in the same jar must not override it.
        from_cookie = False
        if token is None:
            cookie_token = request.cookies.get(SESSION_COOKIE)
            if cookie_token:
                token = cookie_token
                from_cookie = True

        if token is None:
            request.state.org_id = None
            request.state.user_id = None
            request.state.role = None
            return await call_next(request)

        # CSRF only applies to cookie auth. A Bearer header is not attached
        # automatically by the browser, so a cross-site page cannot forge it and
        # there is nothing to protect against. Safe methods are exempt: they are
        # not supposed to change state, and gating them would break plain
        # navigation to the API.
        if from_cookie and request.method not in SAFE_METHODS:
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get(CSRF_HEADER)
            if not csrf_cookie or not csrf_header or not secrets.compare_digest(
                csrf_cookie, csrf_header
            ):
                logger.warning(
                    "CSRF check failed for %s %s", request.method, request.url.path
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"},
                )

        try:
            org_id, user_id, role = self._resolve_credentials(token)
            request.state.org_id = org_id
            request.state.user_id = user_id
            request.state.role = role
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
            )

        return await call_next(request)

    @staticmethod
    def _extract_token(auth_header: str) -> Optional[str]:
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    @staticmethod
    def _resolve_credentials(token: str) -> tuple[str, int, str]:
        """Resolve a token to (org_id, user_id, role).

        Tries API key first if it has the orion prefix, else JWT.
        Raises HTTPException(401) on failure.
        """
        if token.startswith(API_KEY_PREFIX):
            return _resolve_api_key(token)
        return _resolve_jwt(token)


def _resolve_jwt(token: str) -> tuple[str, int, str]:
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id_str = payload.get("sub")
    org_id = payload.get("org_id")
    role = payload.get("role")
    if user_id_str is None or org_id is None or role is None:
        raise HTTPException(status_code=401, detail="Token missing org claims")
    try:
        user_id = int(str(user_id_str))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token subject")
    return str(org_id), user_id, str(role)


def _resolve_api_key(plaintext: str) -> tuple[str, int, str]:
    key_hash = hash_api_key(plaintext)
    session = get_session()
    try:
        repo = ApiKeyRepository(session)
        key = repo.get_by_hash(key_hash)
        if key is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        repo.touch(key.id)
        # Look up role from the user record
        user = session.query(UserRecord).filter_by(id=key.user_id).first()
        role = user.role if user is not None else "member"
        org_id = key.org_id
        user_id = key.user_id
        session.commit()
        return org_id, user_id, role
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SUPERADMIN_ROLE = "superadmin"


def is_superadmin(request: Request) -> bool:
    return getattr(request.state, "role", None) == SUPERADMIN_ROLE


def require_role(*allowed_roles: str):
    """Dependency factory that enforces a minimum role on a route.

    Superadmin always passes regardless of allowed_roles.
    """
    def _check(request: Request):
        role = getattr(request.state, "role", None)
        if role == SUPERADMIN_ROLE:
            return
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {allowed_roles}. Your role: {role}",
            )
    return _check


def require_superadmin():
    """Dependency factory that restricts a route to superadmins only."""
    def _check(request: Request):
        role = getattr(request.state, "role", None)
        if role != SUPERADMIN_ROLE:
            raise HTTPException(
                status_code=403,
                detail="Requires superadmin role",
            )
    return _check


def require_plan(*allowed_plans: str):
    """Dependency factory that enforces a subscription plan on a route.

    Superadmin bypass: any plan check is waived for superadmin role.
    Usage: `_=Depends(require_plan("pro", "enterprise"))`.
    """
    from arep.database.repository import OrganisationRepository

    def _check(request: Request):
        if is_superadmin(request):
            return
        org_id = getattr(request.state, "org_id", None)
        if not org_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        session = get_session()
        try:
            org = OrganisationRepository(session).get_by_id(org_id)
            if org is None:
                raise HTTPException(status_code=401, detail="Organisation not found")
            if org.plan not in allowed_plans:
                raise HTTPException(
                    status_code=402,
                    detail=f"Requires one of: {allowed_plans}. Current plan: {org.plan}",
                )
        finally:
            session.close()
    return _check


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Attach baseline security headers to every response (Phase 0.3, defect D-03).

    This is an API, not an HTML app, so the headers are the ones that matter for
    a JSON surface plus the two doc pages:

      - ``X-Content-Type-Options: nosniff`` — stop a browser from re-typing a
        JSON error body as HTML and running it.
      - ``X-Frame-Options: DENY`` — nothing here is meant to be framed.
      - ``Referrer-Policy: no-referrer`` — URLs carry run ids and (until 0.4)
        WS tickets; don't leak them to third parties.
      - ``Content-Security-Policy: default-src 'none'`` — a JSON response has no
        business loading anything. Relaxed for /docs and /redoc, which are real
        HTML pages pulling Swagger/ReDoc bundles from a CDN.
      - ``Strict-Transport-Security`` — only over HTTPS. Sending it over plain
        HTTP is ignored by browsers and would break local dev over http://.
    """

    # Swagger UI and ReDoc load their JS/CSS from jsdelivr and inline a bootstrap
    # script; a default-src 'none' policy would render both pages blank.
    _DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
    _DOC_CSP = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "connect-src 'self'"
    )
    _API_CSP = "default-src 'none'; frame-ancestors 'none'"

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")

        path = request.url.path
        is_docs = any(path.startswith(p) for p in self._DOC_PATHS)
        response.headers.setdefault(
            "Content-Security-Policy",
            self._DOC_CSP if is_docs else self._API_CSP,
        )

        # HSTS is meaningless (and ignored) over http://; only assert it when the
        # request actually arrived over TLS, directly or via a trusted proxy.
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
