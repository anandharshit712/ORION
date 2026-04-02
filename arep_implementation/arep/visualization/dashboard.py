"""
ORION Dashboard Server.

Serves the web dashboard and integrates with the REST API.
Can run standalone or be mounted on the FastAPI app.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from arep.utils.logging_config import get_logger

logger = get_logger("visualization.dashboard")

TEMPLATES_DIR = Path(__file__).parent / "templates"


def mount_dashboard(app: FastAPI) -> None:
    """
    Mount the dashboard routes on an existing FastAPI app.

    Args:
        app: The FastAPI application to mount on.
    """

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve the main dashboard page."""
        html_path = TEMPLATES_DIR / "dashboard.html"
        if not html_path.exists():
            return HTMLResponse(
                "<h1>Dashboard template not found</h1>",
                status_code=500,
            )
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_alt():
        """Alternative dashboard URL."""
        return await dashboard()

    logger.info("Dashboard mounted at / and /dashboard")


def create_dashboard_app() -> FastAPI:
    """
    Create a standalone dashboard application.

    Includes both the API routes and dashboard serving.
    """
    from arep.api.app import create_app

    app = create_app()
    mount_dashboard(app)
    return app


if __name__ == "__main__":
    import sys
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
    app = create_dashboard_app()
    print(f"\n  ORION Dashboard: http://localhost:{port}")
    print(f"  API Docs:       http://localhost:{port}/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
