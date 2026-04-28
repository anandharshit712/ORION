"""
ORION FastAPI Application Factory.

Creates the ORION REST API application with:
  - CORS middleware
  - All API routers mounted
  - Database initialization on startup
  - OpenAPI documentation
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arep.api.auth import auth_router
from arep.api.middleware import OrgAuthMiddleware
from arep.api.models_routes import models_api_router
from arep.api.orgs import keys_router, orgs_router
from arep.api.routes import (
    health_router, models_router, scenarios_router,
    evaluate_router, jobs_router, results_router, runs_router,
)
from arep.api.ws import ws_router
from arep.database.connection import init_database
from arep.utils.logging_config import get_logger

logger = get_logger("api.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: initialize DB on startup."""
    logger.info("ORION API starting up...")
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

    # Org-scoped auth middleware (added BEFORE CORS so it runs AFTER CORS in Starlette's
    # reverse-add semantics — CORS sees requests first, auth resolves before route handlers).
    app.add_middleware(OrgAuthMiddleware)

    # CORS (outermost — handles preflight OPTIONS without auth)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    app.include_router(auth_router)
    app.include_router(orgs_router)
    app.include_router(keys_router)
    app.include_router(models_api_router)
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
