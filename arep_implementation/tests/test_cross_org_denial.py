"""
Cross-org denial across every authenticated route group (Phase 0.6, D-09).

test_multitenancy.py covers the runs and keys paths. This walks the rest —
admin, models, billing, batch status, live runs — because tenancy isolation is
the one property where a single unguarded route is the whole failure: a
customer reading another customer's evaluation results is the end of the
product, regardless of how well the other forty routes behave.

The rule under test throughout: org A must get 404 or 403 for anything owned by
org B, and never a 200 with B's data. 404 rather than 403 wherever the id would
otherwise be confirmed to exist.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    # Run Celery tasks inline: the batch route enqueues, and without this the
    # test needs a live Redis.
    from arep.worker.celery_app import celery_app

    celery_app.conf.task_always_eager = True

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


def _account(client, slug: str) -> dict:
    """Create a verified org + owner and return its auth material."""
    email = f"{slug}@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": slug,
            "password": PASSWORD,
            "org_name": f"{slug} org",
            "org_slug": slug,
        },
    )
    assert r.status_code == 201, r.text
    verify_email_for(email)

    client.cookies.clear()
    r = client.post("/api/auth/login", json={"identifier": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # header auth only, so the jar cannot leak identity

    return {
        "org_id": r.json()["org_id"],
        "headers": {"Authorization": f"Bearer {r.json()['access_token']}"},
    }


@pytest.fixture(scope="module")
def org_a(client):
    return _account(client, "alpha")


@pytest.fixture(scope="module")
def org_b(client):
    return _account(client, "bravo")


@pytest.fixture(autouse=True)
def no_cookie_identity(client):
    """Every request in this module authenticates by header, never by a cookie
    left over from a previous test."""
    client.cookies.clear()
    yield
    client.cookies.clear()


# -- Org profile ----------------------------------------------------------


def test_each_org_sees_only_itself(client, org_a, org_b):
    a = client.get("/api/orgs/me", headers=org_a["headers"]).json()
    b = client.get("/api/orgs/me", headers=org_b["headers"]).json()
    assert a["id"] != b["id"]
    assert a["slug"] == "alpha"
    assert b["slug"] == "bravo"


# -- Models ---------------------------------------------------------------


def test_model_list_is_org_scoped(client, org_a, org_b):
    r = client.post(
        "/api/models/register",
        headers=org_a["headers"],
        json={
            "name": "alpha-model",
            "version": "v1",
            "image": "example.com/a:v1",
        },
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    b_models = client.get("/api/models/", headers=org_b["headers"]).json()
    assert all(m["id"] != model_id for m in b_models), "B can see A's model"


def test_cross_org_model_fetch_is_404(client, org_a, org_b):
    r = client.post(
        "/api/models/register",
        headers=org_a["headers"],
        json={
            "name": "alpha-private",
            "version": "v1",
            "image": "example.com/p:v1",
        },
    )
    model_id = r.json()["id"]

    r = client.get(f"/api/models/{model_id}", headers=org_b["headers"])
    assert r.status_code == 404, "403 would confirm the model exists"


def test_cross_org_model_delete_is_refused(client, org_a, org_b):
    r = client.post(
        "/api/models/register",
        headers=org_a["headers"],
        json={
            "name": "alpha-keepme",
            "version": "v1",
            "image": "example.com/k:v1",
        },
    )
    model_id = r.json()["id"]

    assert (
        client.delete(f"/api/models/{model_id}", headers=org_b["headers"]).status_code
        == 404
    )
    # ...and it is still there for its owner.
    assert (
        client.get(f"/api/models/{model_id}", headers=org_a["headers"]).status_code
        == 200
    )


# -- API keys -------------------------------------------------------------


def test_key_listing_is_org_scoped(client, org_a, org_b):
    client.post("/api/keys/", headers=org_a["headers"], json={"label": "alpha-key"})
    b_keys = client.get("/api/keys/", headers=org_b["headers"]).json()
    assert all(k["label"] != "alpha-key" for k in b_keys)


def test_an_api_key_authenticates_only_its_own_org(client, org_a, org_b):
    created = client.post(
        "/api/keys/", headers=org_a["headers"], json={"label": "scoped"}
    )
    assert created.status_code == 201, created.text
    key = created.json()["plaintext"]  # shown once, at creation

    me = client.get("/api/orgs/me", headers={"Authorization": f"Bearer {key}"})
    assert me.status_code == 200
    assert me.json()["id"] == org_a["org_id"], "A's key resolved to another org"


# -- Batches and results --------------------------------------------------


def test_cross_org_batch_status_is_404(client, org_a, org_b):
    r = client.post(
        "/api/runs/batch",
        headers=org_a["headers"],
        json={
            "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
            "model_name": "EmergencyBrake",
            "num_runs": 1,
            "master_seed": 7,
        },
    )
    assert r.status_code == 202, r.text
    batch_id = r.json()["batch_id"]

    assert (
        client.get(
            f"/api/runs/batch/{batch_id}/status", headers=org_b["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/runs/batch/{batch_id}/status", headers=org_a["headers"]
        ).status_code
        == 200
    )


def test_job_listing_does_not_leak_across_orgs(client, org_a, org_b):
    a_jobs = client.get("/jobs/", headers=org_a["headers"]).json()
    b_jobs = client.get("/jobs/", headers=org_b["headers"]).json()
    a_ids = {j["id"] for j in a_jobs}
    b_ids = {j["id"] for j in b_jobs}
    assert not (a_ids & b_ids), "a batch job appeared in both orgs' listings"


def test_results_by_batch_are_org_scoped(client, org_a, org_b):
    a_jobs = client.get("/jobs/", headers=org_a["headers"]).json()
    if not a_jobs:
        pytest.skip("no batch job to check against")
    batch_id = a_jobs[0]["id"]

    b_rows = client.get(f"/results/batch/{batch_id}", headers=org_b["headers"])
    assert b_rows.status_code in (200, 404)
    if b_rows.status_code == 200:
        assert b_rows.json() == [], "B read run rows from A's batch"


# -- Live runs ------------------------------------------------------------


def test_cross_org_live_run_is_404(client, org_a, org_b):
    import asyncio

    from arep.api.sim_registry import LiveRun, get_registry

    run = LiveRun(
        run_id="alpha-live-run",
        scenario_path="x",
        scenario_name="x",
        model_name="EmergencyBrake",
        master_seed=1,
        status="running",
        started_at="2026-09-20T00:00:00Z",
        org_id=org_a["org_id"],
    )
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        get_registry().register(run)
    )

    assert (
        client.get("/api/runs/alpha-live-run", headers=org_b["headers"]).status_code
        == 404
    )
    assert (
        client.get("/api/runs/alpha-live-run", headers=org_a["headers"]).status_code
        == 200
    )


def test_cross_org_ws_ticket_is_refused(client, org_a, org_b):
    """A ticket for someone else's run would hand over their live telemetry."""
    assert (
        client.post(
            "/api/runs/alpha-live-run/ws-ticket", headers=org_b["headers"]
        ).status_code
        == 404
    )


def test_cross_org_run_cancel_is_refused(client, org_a, org_b):
    assert (
        client.delete("/api/runs/alpha-live-run", headers=org_b["headers"]).status_code
        == 404
    )


def test_live_run_listing_is_org_scoped(client, org_a, org_b):
    b_runs = client.get("/api/runs/", headers=org_b["headers"]).json()
    assert all(r["run_id"] != "alpha-live-run" for r in b_runs)


# -- Admin ----------------------------------------------------------------


def test_admin_routes_reject_a_normal_owner(client, org_a):
    """Org owner is not platform superadmin — the two must not be conflated."""
    r = client.put(
        f"/api/admin/orgs/{org_a['org_id']}/pickle-models",
        headers=org_a["headers"],
        json={"enabled": True},
    )
    assert r.status_code == 403


def test_a_normal_owner_cannot_grant_itself_credits(client, org_a):
    before = client.get("/api/orgs/me", headers=org_a["headers"]).json()["run_credits"]

    r = client.post(
        f"/api/admin/orgs/{org_a['org_id']}/credits",
        headers=org_a["headers"],
        json={"add_credits": 100_000},
    )
    assert r.status_code in (403, 404, 405)

    after = client.get("/api/orgs/me", headers=org_a["headers"]).json()["run_credits"]
    assert after == before


# -- Unauthenticated ------------------------------------------------------


def test_no_token_reaches_nothing(client):
    for method, path in [
        ("GET", "/api/orgs/me"),
        ("GET", "/api/keys/"),
        ("GET", "/api/models/"),
        ("GET", "/jobs/"),
        ("GET", "/api/runs/"),
        ("GET", "/scenarios/"),
    ]:
        r = client.request(method, path)
        assert r.status_code == 401, f"{method} {path} answered {r.status_code}"
