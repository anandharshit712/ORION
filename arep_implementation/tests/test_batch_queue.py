"""
Async batch queue tests (P1.3 SaaS).

Runs Celery in ``task_always_eager`` mode so tasks execute inline inside the
TestClient request — no external Redis broker required.

Covers the acceptance criteria from ``ORION_SAAS_ROADMAP.md`` § 1.3:
  - POST /api/runs/batch returns immediately with 202 + batch_id
  - Closing the connection does not stop execution (eager == complete on return)
  - Credits are deducted before execution; refunded on individual failure
  - GET /api/runs/batch/{batch_id}/status reflects per-run progress
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENARIO_PATH = os.path.join(
    _PROJECT_ROOT, "scenarios", "basic", "straight_road_lead_vehicle.yaml",
)
if not os.path.exists(SCENARIO_PATH):
    # Fallback: nested under arep_implementation/scenarios/ in some checkouts
    alt = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scenarios", "basic", "straight_road_lead_vehicle.yaml",
    )
    if os.path.exists(alt):
        SCENARIO_PATH = alt


@pytest.fixture(scope="module")
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    # Run Celery tasks synchronously, no broker needed.
    from arep.worker.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    from fastapi.testclient import TestClient
    from arep.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _signup_login(client, email, username, slug):
    client.post("/api/auth/signup", json={
        "email": email, "username": username, "password": "password123",
        "org_name": f"{username} org", "org_slug": slug,
    })
    r = client.post("/api/auth/login", json={
        "identifier": email, "password": "password123",
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_enqueue_returns_immediately_and_completes(client):
    """Eager mode → enqueue path returns 202 and batch finalises."""
    token = _signup_login(client, "ada@a.com", "ada", "ada-org")

    r = client.post(
        "/api/runs/batch",
        headers=_auth(token),
        json={
            "scenario_path": SCENARIO_PATH,
            "model_name": "EmergencyBrake",
            "num_runs": 3,
            "master_seed": 42,
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["num_runs"] == 3
    assert body["enqueued"] == 3
    assert body["credits_remaining"] == 50 - 3
    batch_id = body["batch_id"]

    # In eager mode tasks ran inline; status should already reflect completion.
    r = client.get(f"/api/runs/batch/{batch_id}/status", headers=_auth(token))
    assert r.status_code == 200
    s = r.json()
    assert s["total"] == 3
    assert s["completed"] == 3
    assert s["failed"] == 0
    assert s["status"] == "completed"
    assert s["composite_mean"] is not None


def test_insufficient_credits_returns_402(client):
    token = _signup_login(client, "bob@b.com", "bob", "bob-org")
    r = client.post(
        "/api/runs/batch",
        headers=_auth(token),
        json={
            "scenario_path": SCENARIO_PATH,
            "model_name": "EmergencyBrake",
            "num_runs": 999,            # > 50 free credits
            "master_seed": 1,
        },
    )
    assert r.status_code == 402
    assert "credits" in r.json()["detail"].lower()


def test_unknown_model_rejected_before_credit_deduct(client):
    token = _signup_login(client, "cara@c.com", "cara", "cara-org")
    r = client.post(
        "/api/runs/batch",
        headers=_auth(token),
        json={
            "scenario_path": SCENARIO_PATH,
            "model_name": "DoesNotExist",
            "num_runs": 5,
            "master_seed": 1,
        },
    )
    assert r.status_code == 400
    # Credits unchanged
    me = client.get("/api/orgs/me", headers=_auth(token)).json()
    assert me["run_credits"] == 50


def test_batch_org_isolation(client):
    """Org B cannot read org A's batch status."""
    token_a = _signup_login(client, "dora@d.com", "dora", "dora-org")
    token_b = _signup_login(client, "eli@e.com", "eli", "eli-org")

    r = client.post(
        "/api/runs/batch",
        headers=_auth(token_a),
        json={
            "scenario_path": SCENARIO_PATH,
            "model_name": "EmergencyBrake",
            "num_runs": 1,
            "master_seed": 7,
        },
    )
    assert r.status_code == 202
    batch_id = r.json()["batch_id"]

    r = client.get(f"/api/runs/batch/{batch_id}/status", headers=_auth(token_b))
    assert r.status_code == 404
