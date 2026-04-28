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

from arep.api.auth import decode_access_token
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
}

# Path prefixes that bypass middleware (WebSocket auth handled separately)
PUBLIC_PREFIXES = (
    "/ws/",
)


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

        if token is None:
            request.state.org_id = None
            request.state.user_id = None
            request.state.role = None
            return await call_next(request)

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
