"""
Model comparison over HTTP (Phase 2.4).

`RegressionDetector` has worked since Phase 2 but was CLI-only, so the feature
did not exist as far as a customer was concerned and the acceptance criterion
about credit accounting could not be met at all.

What these tests pin is the money and the tenancy. The comparison logic itself
is covered by `test_regression_detector.py`; what is new here is that a
comparison is charged before it runs, refunded when it fails, and invisible to
another org.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.api.compare import comparison_cost  # noqa: E402
from tests.conftest import verify_email_for  # noqa: E402

SCENARIO = "../scenarios/lon/LON-003_emergency_stop.yaml"


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


@pytest.fixture(scope="module")
def account(client):
    """One shared account — signup is rate limited to 3/hour/IP."""
    email = "compare@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "comparer",
            "password": "password123",
            "org_name": "compare org",
            "org_slug": "compare",
        },
    )
    verify_email_for(email)
    login = client.post(
        "/api/auth/login", json={"identifier": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    org_id = client.get("/api/orgs/me", headers=headers).json()["id"]
    return headers, org_id


def _set_credits(org_id, amount):
    from arep.database.connection import session_scope
    from arep.database.models import OrganisationRecord

    with session_scope() as db:
        org = db.get(OrganisationRecord, org_id)
        org.run_credits = amount


def _credits(org_id):
    from arep.database.connection import session_scope
    from arep.database.models import OrganisationRecord

    with session_scope() as db:
        return db.get(OrganisationRecord, org_id).run_credits


# -- The cost formula ------------------------------------------------------


def test_the_cost_is_two_models_times_runs_times_scenarios():
    """The acceptance criterion, stated as arithmetic:
    `2 x runs_per_scenario x len(scenario_ids)`."""
    assert comparison_cost(runs_per_scenario=10, scenario_count=3) == 60
    assert comparison_cost(runs_per_scenario=1, scenario_count=1) == 2


def test_a_comparison_charges_before_it_runs(client, account):
    """Charging on completion would let a customer queue unlimited work."""
    headers, org_id = account
    _set_credits(org_id, 100)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "ConstantAction",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 2,
            "seed": 42,
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()

    assert body["credits_charged"] == 4  # 2 models x 2 runs x 1 scenario
    assert body["credits_remaining"] == 96
    assert _credits(org_id) == 96


def test_an_org_without_enough_credits_is_refused(client, account):
    headers, org_id = account
    _set_credits(org_id, 3)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "ConstantAction",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 2,
            "seed": 42,
        },
    )
    assert r.status_code == 402
    # The message has to say what it would have cost, or the customer cannot
    # tell how many credits to buy.
    assert "4 credits" in r.json()["detail"]
    assert _credits(org_id) == 3, "a refused comparison must not charge"


def test_a_failed_comparison_refunds_what_it_charged(client, account):
    """Refunded from the recorded charge, not a recomputed cost: the pricing
    formula can change between charge and refund."""
    headers, org_id = account
    _set_credits(org_id, 50)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "NoSuchModelAtAll",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 2,
            "seed": 42,
        },
    )
    assert r.status_code == 202, r.text
    comparison_id = r.json()["comparison_id"]

    status = client.get(f"/api/compare/{comparison_id}", headers=headers).json()
    assert status["status"] == "failed"
    assert status["error_message"]
    assert _credits(org_id) == 50, "a failed comparison must refund its charge"


# -- The result ------------------------------------------------------------


def test_a_comparison_completes_and_names_a_winner(client, account):
    headers, org_id = account
    _set_credits(org_id, 100)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "ConstantAction",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 2,
            "seed": 42,
        },
    )
    comparison_id = r.json()["comparison_id"]

    status = client.get(f"/api/compare/{comparison_id}", headers=headers).json()
    assert status["status"] == "completed", status.get("error_message")
    # ConstantAction drives into a braking lead vehicle; it must not win.
    assert status["overall_winner"] in ("a", "tie")
    assert status["recommendation"]
    assert status["report"]["scenario_comparisons"], "the report has no comparisons"


def test_the_list_view_omits_the_full_report(client, account):
    """It is large and no list renders it."""
    headers, _ = account
    rows = client.get("/api/compare/", headers=headers).json()
    assert rows, "no comparisons listed"
    assert all(row["report"] is None for row in rows)


# -- Validation and tenancy ------------------------------------------------


def test_comparing_a_model_against_itself_is_refused(client, account):
    headers, org_id = account
    _set_credits(org_id, 100)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "EmergencyBrake",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 2,
        },
    )
    assert r.status_code == 400
    assert _credits(org_id) == 100, "a refused request must not charge"


def test_an_empty_scenario_list_is_refused(client, account):
    headers, _ = account
    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "ConstantAction",
            "scenario_ids": [],
        },
    )
    assert r.status_code == 422


def test_another_orgs_comparison_is_not_readable(client, account):
    headers, org_id = account
    _set_credits(org_id, 100)

    r = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": "EmergencyBrake",
            "model_b_id": "ConstantAction",
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 1,
        },
    )
    comparison_id = r.json()["comparison_id"]

    from arep.database.connection import session_scope
    from arep.database.models import ComparisonJobRecord

    with session_scope() as db:
        db.get(ComparisonJobRecord, comparison_id).org_id = "someone-else"

    assert (
        client.get(f"/api/compare/{comparison_id}", headers=headers).status_code == 404
    )


def test_the_endpoint_requires_auth(client):
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/compare/1").status_code == 401
        assert anonymous.post("/api/compare/", json={}).status_code == 401
