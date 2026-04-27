"""
ORION API Middleware.  [Phase 1]

Org-scoped authentication middleware.
Resolves both JWT tokens and API keys to (org_id, user_id, role)
and attaches them to the request state for downstream route handlers.

Every protected route reads from request.state.org_id — it never
inspects the token itself.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from arep.utils.logging_config import get_logger

logger = get_logger("api.middleware")

# Routes that do NOT require authentication
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
    "/api/auth/signup",
}


class OrgAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that resolves auth credentials on every request.

    Resolution order:
      1. Authorization: Bearer <jwt>   → decode JWT, extract org_id + role
      2. Authorization: Bearer <api_key>  → hash lookup in api_keys table
      3. Public path  → skip auth entirely

    On success, sets:
      request.state.org_id  : str (UUID)
      request.state.user_id : str (UUID)
      request.state.role    : str  ("owner" | "admin" | "member" | "viewer")

    On failure, returns 401.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip auth for public paths and OPTIONS preflight
        if request.method == "OPTIONS" or path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token = self._extract_token(auth_header)

        if token is None:
            # Allow unauthenticated requests to pass through to routes
            # that may have their own optional auth logic.
            request.state.org_id = None
            request.state.user_id = None
            request.state.role = None
            return await call_next(request)

        try:
            org_id, user_id, role = await self._resolve_credentials(token, request)
            request.state.org_id = org_id
            request.state.user_id = user_id
            request.state.role = role
        except HTTPException as e:
            from starlette.responses import JSONResponse
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
    async def _resolve_credentials(
        token: str, request: Request
    ) -> tuple[str, str, str]:
        """
        Resolve a token to (org_id, user_id, role).

        Tries JWT first; falls back to API key lookup.
        Raises HTTPException(401) if neither succeeds.
        """
        # TODO [P1]: Implement JWT decode → extract org_id, user_id, role
        # TODO [P1]: If JWT fails, hash token and look up in api_keys table
        # TODO [P1]: Return (org_id, user_id, role) tuple
        raise NotImplementedError("OrgAuthMiddleware._resolve_credentials not yet implemented")


def require_role(*allowed_roles: str):
    """
    Dependency factory that enforces a minimum role on a route.

    Usage:
        @router.post("/admin/thing")
        def admin_thing(request: Request, _=Depends(require_role("owner", "admin"))):
            ...
    """
    def _check(request: Request):
        role = getattr(request.state, "role", None)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {allowed_roles}. Your role: {role}",
            )
    return _check


def require_plan(*allowed_plans: str):
    """
    Dependency factory that enforces a subscription plan on a route.

    Usage:
        @router.post("/api/search")
        def adversarial_search(request: Request, _=Depends(require_plan("pro", "enterprise"))):
            ...
    """
    def _check(request: Request):
        # TODO [P1]: Load org plan from DB or request.state and check against allowed_plans
        # TODO [P1]: Raise HTTPException(402, "Requires Pro or Enterprise plan") if not allowed
        pass
    return _check
