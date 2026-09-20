"""
Route authentication tests (Phase 0.3, defect D-07).

The roadmap listed /models/, /scenarios/, /jobs/ and /results/* as
unauthenticated. Probing the running app showed only the first two actually
were — /jobs/ and /results/* already called get_request_principal, which 401s.
These tests pin down all four either way, so a refactor cannot quietly reopen
the ones that were already closed.

Auth is declared on the router rather than per handler, so the interesting
case is a *new* route inheriting it: test_every_data_router_requires_auth
walks the mounted routes instead of listing paths by hand.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Routers that serve data and must never answer an anonymous caller.
GATED_PREFIXES = ("/models", "/scenarios", "/evaluate", "/jobs", "/results", "/api/runs")

# Deliberately public: probes and the login surface cannot present a token.
PUBLIC_PATHS = {
    "/health", "/docs", "/redoc", "/openapi.json",
    "/api/auth/login", "/api/auth/signup", "/api/auth/register",
    "/api/auth/forgot-password", "/api/auth/reset-password",
}


@pytest.fixture(scope="module")
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    from fastapi.testclient import TestClient
    from arep.api.app import create_app

    with TestClient(create_app()) as c:
        yield c

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture(scope="module")
def token(client):
    """A real JWT, so the positive cases prove the gate opens for a valid caller."""
    r = client.post("/api/auth/signup", json={
        "email": "auth-test@example.com",
        "username": "authtest",
        "password": "correct-horse-battery",
        "org_name": "Auth Test Org",
    })
    assert r.status_code == 201, r.text

    r = client.post("/api/auth/login", json={
        "identifier": "auth-test@example.com",
        "password": "correct-horse-battery",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# -- The acceptance criterion ---------------------------------------------

def test_unauthenticated_scenarios_returns_401(client):
    """The D-03/D-07 acceptance criterion, verbatim from the roadmap."""
    assert client.get("/scenarios/").status_code == 401


def test_unauthenticated_model_list_returns_401(client):
    """Closed deliberately: the built-in list enumerates our evaluation surface."""
    assert client.get("/models/").status_code == 401


def test_unauthenticated_scenario_detail_returns_401(client):
    assert client.get("/scenarios/1").status_code == 401


def test_unauthenticated_jobs_and_results_return_401(client):
    """Already true before 0.3 — pinned so it stays true."""
    assert client.get("/jobs/").status_code == 401
    assert client.get("/jobs/1").status_code == 401
    assert client.get("/results/model/EmergencyBrake").status_code == 401
    assert client.get("/results/batch/1").status_code == 401


# -- The gate opens for a valid caller ------------------------------------

def test_authenticated_caller_can_read_scenarios(client, token):
    r = client.get("/scenarios/", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_authenticated_caller_can_read_model_list(client, token):
    r = client.get("/models/", headers=_auth(token))
    assert r.status_code == 200
    assert "EmergencyBrake" in r.json()["models"]


def test_authenticated_caller_can_read_jobs(client, token):
    assert client.get("/jobs/", headers=_auth(token)).status_code == 200


# -- Negative credentials -------------------------------------------------

def test_garbage_token_is_rejected(client):
    r = client.get("/scenarios/", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_api_key_shaped_garbage_is_rejected(client):
    """Keys starting with the sk-orion- prefix take the API-key branch."""
    r = client.get("/scenarios/", headers={"Authorization": "Bearer sk-orion-nope"})
    assert r.status_code == 401


def test_errors_keep_the_platform_error_shape(client):
    body = client.get("/scenarios/").json()
    assert "detail" in body


# -- Public surface stays public ------------------------------------------

def test_health_stays_public(client):
    """A probe cannot hold a token; gating this reads as an outage."""
    assert client.get("/health").status_code == 200


def test_openapi_schema_stays_public(client):
    assert client.get("/openapi.json").status_code == 200


# -- The rule, not the list -----------------------------------------------

def test_every_data_router_requires_auth(client):
    """Walk the mounted routes so a newly added one cannot slip through.

    Listing paths by hand is exactly the failure mode D-07 was: four endpoints
    that nobody remembered to gate.
    """
    from arep.api.app import create_app

    app = create_app()
    unguarded = []

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path in PUBLIC_PATHS or not path.startswith(GATED_PREFIXES):
            continue
        if "GET" not in methods:
            continue            # POST/PUT/DELETE need a body or a real id
        if "{" in path:
            continue            # path params need a valid id; covered above

        if client.get(path).status_code != 401:
            unguarded.append(path)

    assert not unguarded, f"routes answering anonymous callers: {unguarded}"
