"""
ORION FastAPI Application Factory.

Creates the ORION REST API application with:
  - CORS middleware (explicit origin whitelist — D-03)
  - Rate limiting and security headers (D-03)
  - All API routers mounted
  - Database initialization on startup
  - OpenAPI documentation
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from arep.api.admin import admin_router
from arep.api.auth import auth_router
from arep.api.billing import billing_router
from arep.api.middleware import OrgAuthMiddleware, SecurityHeadersMiddleware
from arep.api.ratelimit import limiter, rate_limit_exceeded_handler
from arep.api.compare import compare_router
from arep.api.models_routes import models_api_router
from arep.api.orgs import keys_router, orgs_router
from arep.api.routes import (
    health_router,
    models_router,
    scenarios_router,
    evaluate_router,
    jobs_router,
    results_router,
    runs_router,
)
from arep.api.ws import ws_router
from arep.config.validate import resolve_cors_origins, validate_startup
from arep.database.connection import init_database
from arep.utils.logging_config import get_logger

logger = get_logger("api.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: validate config (fail-fast) then initialize DB."""
    logger.info("ORION API starting up...")
    validate_startup()  # D-02: refuse to boot on missing/insecure secrets
    init_database()
    yield
    logger.info("ORION API shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="ORION - Operational Robustness & Intelligence Optimization Network",
        description=(
            "REST API for evaluating and training autonomous driving models "
            "across safety, compliance, stability, and reactivity metrics."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Rate limiting (D-03). The limiter must be on app.state: slowapi resolves
    # it from there, both in the decorator and in the middleware.
    app.state.limiter = limiter
    # Starlette types a handler as taking Exception; slowapi ships one narrowed
    # to RateLimitExceeded. The registration pairs the two correctly at runtime
    # -- only the declared signatures disagree. `warn_unused_ignores` will flag
    # this line if slowapi ever widens it.
    app.add_exception_handler(
        RateLimitExceeded, rate_limit_exceeded_handler  # type: ignore[arg-type]
    )

    # Starlette runs middleware in REVERSE order of registration, so this block
    # reads bottom-up: CORS first (preflight answered without auth), then
    # security headers, then rate limiting, then org auth closest to the route.
    #
    # Rate limiting sits *after* OrgAuthMiddleware in add order, meaning it runs
    # *before* it — so the default limit is keyed on IP for unauthenticated
    # callers and the per-route limits on authenticated routes still see
    # request.state once the auth middleware has run beneath it.
    app.add_middleware(OrgAuthMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS (outermost). resolve_cors_origins() refuses a wildcard outside dev;
    # allow_credentials=True is only valid against an explicit origin list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
    )

    # Mount routers
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(billing_router)
    app.include_router(orgs_router)
    app.include_router(keys_router)
    app.include_router(models_api_router)
    app.include_router(compare_router)
    app.include_router(health_router)
    app.include_router(models_router)
    app.include_router(scenarios_router)
    app.include_router(evaluate_router)
    app.include_router(jobs_router)
    app.include_router(results_router)
    app.include_router(runs_router)
    app.include_router(ws_router)

    return app


# Uvicorn entry point
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "arep.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
