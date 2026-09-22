"""
Partial batch failure and refund accounting (Phase 0.6, defect D-09).

The roadmap's criterion: 5 runs, 3 fail → exactly 3 credits refunded, and the
batch finalises once.

This is the money path. Credits are deducted up front for the whole batch, so
every run that does not produce a result has to give one back — no more, no
less. Over-refunding gives away free compute; under-refunding charges for work
never delivered; finalising twice can double-count either.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

SCENARIO = "scenarios/basic/straight_road_lead_vehicle.yaml"
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

    from arep.worker.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

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


@pytest.fixture
def account(client):
    """A fresh verified org per test, so credit arithmetic starts clean."""
    import uuid

    slug = f"refund{uuid.uuid4().hex[:8]}"
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
    client.cookies.clear()
    return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


def _credits(client, account) -> int:
    return client.get("/api/orgs/me", headers=account["headers"]).json()["run_credits"]


def test_all_runs_succeed_no_refund(client, account):
    before = _credits(client, account)

    r = client.post(
        "/api/runs/batch",
        headers=account["headers"],
        json={
            "scenario_path": SCENARIO,
            "model_name": "EmergencyBrake",
            "num_runs": 3,
            "master_seed": 100,
        },
    )
    assert r.status_code == 202, r.text

    after = _credits(client, account)
    assert before - after == 3, "three runs delivered, three credits spent"


def test_three_of_five_failures_refund_exactly_three(client, account, monkeypatch):
    """The acceptance criterion."""
    from arep.worker import tasks

    before = _credits(client, account)
    base_seed = 500
    failing = {base_seed + 0, base_seed + 2, base_seed + 4}

    real_resolve = tasks.resolve_model
    seen: list[int] = []

    def selective(model_name, builtins, org_id=None, **kwargs):
        seed = seen[-1] if seen else None
        if seed in failing:
            raise ValueError(f"synthetic failure for seed {seed}")
        return real_resolve(model_name, builtins, org_id=org_id)

    real_execute = tasks.execute_single_run

    def tracking(
        task, batch_id, scenario_id, scenario_path, model_name, seed, org_id=None
    ):
        seen.append(seed)
        return real_execute(
            task, batch_id, scenario_id, scenario_path, model_name, seed, org_id
        )

    monkeypatch.setattr(tasks, "resolve_model", selective)
    monkeypatch.setattr(tasks, "execute_single_run", tracking)

    r = client.post(
        "/api/runs/batch",
        headers=account["headers"],
        json={
            "scenario_path": SCENARIO,
            "model_name": "EmergencyBrake",
            "num_runs": 5,
            "master_seed": base_seed,
        },
    )
    assert r.status_code == 202, r.text
    batch_id = r.json()["batch_id"]

    after = _credits(client, account)
    spent = before - after

    status = client.get(
        f"/api/runs/batch/{batch_id}/status", headers=account["headers"]
    ).json()

    assert status["failed"] == 3, f"expected 3 failures, got {status}"
    assert status["completed"] == 2
    assert spent == 2, f"5 deducted, 3 should be refunded, so 2 net — spent {spent}"


def test_a_fully_failed_batch_refunds_everything(client, account, monkeypatch):
    from arep.worker import tasks

    before = _credits(client, account)

    def always_fail(*a, **k):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(tasks, "resolve_model", always_fail)

    r = client.post(
        "/api/runs/batch",
        headers=account["headers"],
        json={
            "scenario_path": SCENARIO,
            "model_name": "EmergencyBrake",
            "num_runs": 4,
            "master_seed": 900,
        },
    )
    assert r.status_code == 202

    assert (
        _credits(client, account) == before
    ), "nothing was delivered, so nothing should be charged"


def test_the_batch_finalises_once_and_reports_terminal_state(
    client,
    account,
    monkeypatch,
):
    """Double-finalising can double-count the aggregate it writes."""
    from arep.database.connection import session_scope
    from arep.database.repository import BatchJobRepository

    r = client.post(
        "/api/runs/batch",
        headers=account["headers"],
        json={
            "scenario_path": SCENARIO,
            "model_name": "EmergencyBrake",
            "num_runs": 2,
            "master_seed": 1200,
        },
    )
    batch_id = r.json()["batch_id"]

    status = client.get(
        f"/api/runs/batch/{batch_id}/status", headers=account["headers"]
    ).json()
    assert status["status"] in ("completed", "failed")
    assert status["completed"] + status["failed"] == status["total"]

    # Calling finalise again must not move anything.
    with session_scope() as db:
        repo = BatchJobRepository(db)
        before = repo.get_by_id(batch_id, org_id=None)
        snapshot = (
            before.status,
            before.runs_completed,
            before.runs_failed,
            before.composite_mean,
        )
        repo.finalise_if_done(batch_id)

    with session_scope() as db:
        after = BatchJobRepository(db).get_by_id(batch_id, org_id=None)
        assert (
            after.status,
            after.runs_completed,
            after.runs_failed,
            after.composite_mean,
        ) == snapshot


def test_credits_are_deducted_before_execution_not_after(client, account):
    """A client that disconnects mid-request must still be charged correctly."""
    before = _credits(client, account)
    r = client.post(
        "/api/runs/batch",
        headers=account["headers"],
        json={
            "scenario_path": SCENARIO,
            "model_name": "EmergencyBrake",
            "num_runs": 2,
            "master_seed": 1500,
        },
    )
    assert r.status_code == 202
    assert (
        r.json()["credits_remaining"] == before - 2
    ), "the 202 response must report the post-deduction balance"
