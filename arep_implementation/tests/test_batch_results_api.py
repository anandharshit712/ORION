"""
GET /api/runs/batch/{id}/results — the distributions endpoint (Phase 2.1).

Recomputes the summary from the stored per-run rows rather than reading the
means off the batch job. That matters for more than tidiness: the job row holds
only scalars, and recomputing means a batch scored under an older scoring
version is summarised the same way as a new one.

The failures worth catching here are the ones that produce a confident-looking
wrong answer: a batch with no rows reporting a model that scored 0.0, another
org's batch being readable, or the histogram binning over the wrong range.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402


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


def _account(client, name):
    email = f"{name}@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": name,
            "password": "password123",
            "org_name": f"{name} org",
            "org_slug": name,
        },
    )
    verify_email_for(email)
    login = client.post(
        "/api/auth/login", json={"identifier": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_batch(org_id, *, scores, collisions=None, status="completed"):
    """Write a batch job and its run rows straight to the database.

    Faster and far more controllable than running simulations: these tests are
    about how the rows are summarised, not about whether the engine works.
    """
    from arep.database.connection import session_scope
    from arep.database.models import BatchJobRecord, RunRecord, ScenarioRecord

    collisions = collisions or [False] * len(scores)

    with session_scope() as db:
        # content_hash is UNIQUE — one scenario row shared by every batch here,
        # which is also what the real upsert does.
        scenario = (
            db.query(ScenarioRecord)
            .filter(ScenarioRecord.content_hash == "c" * 64)
            .first()
        )
        if scenario is None:
            scenario = ScenarioRecord(
                name="LON-003 Emergency Stop",
                version="1.0",
                content_hash="c" * 64,
                yaml_content="scenario: {}",
                duration=20.0,
                road_type="highway",
                num_traffic_objects=1,
            )
            db.add(scenario)
            db.flush()

        job = BatchJobRecord(
            org_id=org_id,
            scenario_name="LON-003 Emergency Stop",
            model_name="EmergencyBrake",
            num_runs=len(scores),
            master_seed=42,
            status=status,
        )
        db.add(job)
        db.flush()

        for i, (score, collided) in enumerate(zip(scores, collisions)):
            db.add(
                RunRecord(
                    org_id=org_id,
                    scenario_id=scenario.id,
                    batch_job_id=job.id,
                    model_name="EmergencyBrake",
                    master_seed=42 + i,
                    duration=20.0,
                    termination_reason="timeout",
                    composite_score=score,
                    safety_score=score,
                    compliance_score=score,
                    stability_score=score,
                    reactivity_score=score,
                    collision_occurred=collided,
                    min_ttc=1.0 if collided else 8.0,
                )
            )
        db.flush()
        return job.id


def _org_id_of(client, headers):
    return client.get("/api/orgs/me", headers=headers).json()["id"]


@pytest.fixture(scope="module")
def owner(client):
    """The account every test shares.

    Signup is rate limited to 3/hour/IP, so creating one per test would start
    returning 429 partway through the file and every later failure would be a
    lie about the endpoint.
    """
    headers = _account(client, "distros")
    return headers, _org_id_of(client, headers)


@pytest.fixture(scope="module")
def outsider(client):
    """A second org, for the cross-tenant check only."""
    return _account(client, "outsider")


# -- The happy path -------------------------------------------------------


def test_every_metric_comes_back_with_an_interval(client, owner):
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[0.7, 0.8, 0.9, 0.6, 0.75])

    r = client.get(f"/api/runs/batch/{batch}/results", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["scored_runs"] == 5
    for metric in (
        "composite",
        "safety",
        "compliance",
        "stability",
        "reactivity",
        "min_ttc",
    ):
        d = body["distributions"][metric]
        assert d["n"] == 5
        assert d["ci_95_low"] <= d["mean"] <= d["ci_95_high"]
        assert d["minimum"] <= d["percentile_5"]
        assert d["percentile_95"] <= d["maximum"]


def test_the_collision_rate_carries_a_wilson_interval(client, owner):
    headers, org_id = owner
    batch = _seed_batch(
        org_id,
        scores=[0.9] * 8 + [0.2, 0.3],
        collisions=[False] * 8 + [True, True],
    )

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()

    assert body["collision_rate"] == pytest.approx(0.2)
    assert 0.0 <= body["collision_rate_ci_95_low"] <= 0.2
    assert 0.2 <= body["collision_rate_ci_95_high"] <= 1.0


def test_the_worst_run_is_the_one_that_crashed(client, owner):
    """Even when another run scored lower — the crash is the finding."""
    headers, org_id = owner
    batch = _seed_batch(
        org_id,
        scores=[0.10, 0.55, 0.95],
        collisions=[False, True, False],
    )

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()

    assert body["worst_run_seed"] == 43, "the crashed run is the one to reproduce"
    assert body["best_run_seed"] == 44


def test_the_histogram_bins_the_whole_scale(client, owner):
    """Binned over [0, 1] rather than over the observed range: two batches must
    be comparable bin for bin, which they are not if the edges move."""
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[0.05, 0.55, 0.95])

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()
    bins = body["histogram"]

    assert len(bins) == 10
    assert bins[0]["lower"] == pytest.approx(0.0)
    assert bins[-1]["upper"] == pytest.approx(1.0)
    assert sum(b["count"] for b in bins) == 3


# -- Honest edges ---------------------------------------------------------


def test_a_batch_with_no_rows_reports_nothing_rather_than_zeros(client, owner):
    """A queued batch summarised as all-zero scores would read as a model that
    failed everything, which is the opposite of the truth."""
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[], status="queued")

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()

    assert body["scored_runs"] == 0
    assert body["distributions"] == {}
    assert body["low_confidence"] is True


def test_a_small_batch_is_flagged_low_confidence(client, owner):
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[0.7, 0.8])

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()
    assert body["low_confidence"] is True


def test_a_large_batch_is_not_flagged(client, owner):
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[0.7] * 40)

    body = client.get(f"/api/runs/batch/{batch}/results", headers=headers).json()
    assert body["low_confidence"] is False


# -- Access control -------------------------------------------------------


def test_another_orgs_batch_is_not_readable(client, owner, outsider):
    headers, org_id = owner
    batch = _seed_batch(org_id, scores=[0.8, 0.9])

    assert (
        client.get(f"/api/runs/batch/{batch}/results", headers=outsider).status_code
        == 404
    )
    assert (
        client.get(f"/api/runs/batch/{batch}/results", headers=headers).status_code
        == 200
    )


def test_the_endpoint_requires_auth(client):
    """A fresh client, because the shared one holds the session cookie login
    set — reusing it would authenticate the request and 404 on a missing batch,
    which looks like a passing auth check and is not one."""
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/runs/batch/1/results").status_code == 401


def test_an_unknown_batch_is_a_404(client, owner):
    headers, _ = owner
    assert (
        client.get("/api/runs/batch/999999/results", headers=headers).status_code == 404
    )
