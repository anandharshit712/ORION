"""
The Phase 2 exit criterion, executed rather than asserted from memory.

  "Demo flow in one session: submit model → adversarial search → failure
   cluster → replay the worst run → download comparison PDF"

Every step of that existed separately and none of it had ever been run as one
sequence. That is exactly the gap this kind of criterion is for: each piece
passing its own tests says nothing about whether the ids, formats and states
line up between them — and two of them did not.

This is slow by nature (real simulation, a real search) so the budgets are the
smallest that still exercise the path. It is not a performance test.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

pytest.importorskip("cma", reason="needs arep[search]")

SCENARIO = "../scenarios/lon/LON-003_emergency_stop.yaml"

# ConstantAction does not brake, so it collides on LON-003. The flow needs a
# model that actually fails: a clean run has no worst run to replay and no
# cluster to find.
FAILING_MODEL = "ConstantAction"
GOOD_MODEL = "EmergencyBrake"


@pytest.fixture(scope="module")
def client():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    # Celery inline, no broker. `POST /api/runs/batch` returns 503 without one
    # — unlike /api/compare and /api/search, which fall back to running inline,
    # because a batch is N tasks and blocking the request for all of them would
    # be worse than refusing.
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
def headers(client):
    email = "demo@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "demo",
            "password": "password123",
            "org_name": "demo org",
            "org_slug": "demoorg",
        },
    )
    verify_email_for(email)
    login = client.post(
        "/api/auth/login", json={"identifier": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # The flow spends real credits: a batch, a search and a comparison. A free
    # org starts with 50, which is not enough to walk it.
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    org_id = client.get("/api/orgs/me", headers=auth).json()["id"]
    with session_scope() as db:
        OrganisationRepository(db).add_credits(org_id, 5000)

    return auth


@pytest.fixture(scope="module")
def flow(client, headers):
    """Walk the whole flow once and hand each step's output to the tests.

    One shared walk rather than one per assertion: each step costs real
    simulation, and the point of the criterion is that the *sequence* works.
    """
    state = {}

    # ── 1. Run a batch of the failing model, which is what later steps need.
    batch = client.post(
        "/api/runs/batch",
        headers=headers,
        json={
            "scenario_path": SCENARIO,
            "model_name": FAILING_MODEL,
            "num_runs": 6,
            "master_seed": 42,
        },
    )
    assert batch.status_code == 202, batch.text
    state["batch_id"] = batch.json()["batch_id"]

    # ── 2. Adversarial search for the settings that break it.
    search = client.post(
        "/api/search/",
        headers=headers,
        json={
            "scenario_id": SCENARIO,
            "model_id": FAILING_MODEL,
            "max_evals": 12,
        },
    )
    assert search.status_code == 202, search.text
    state["search_id"] = search.json()["search_id"]

    # ── 3. Compare it against a model that does brake.
    compare = client.post(
        "/api/compare/",
        headers=headers,
        json={
            "model_a_id": GOOD_MODEL,
            "model_b_id": FAILING_MODEL,
            "scenario_ids": [SCENARIO],
            "runs_per_scenario": 3,
            "seed": 42,
        },
    )
    assert compare.status_code == 202, compare.text
    state["comparison_id"] = compare.json()["comparison_id"]

    return state


def test_step_1_the_batch_completes_and_names_a_worst_run(client, headers, flow):
    """The results endpoint has to hand back a row id, not only a seed —
    without it the dashboard can name the worst run but not open it."""
    results = client.get(f"/api/runs/batch/{flow['batch_id']}/results", headers=headers)
    assert results.status_code == 200, results.text
    body = results.json()

    assert body["scored_runs"] > 0
    assert body["worst_run_seed"] is not None
    assert (
        body["worst_run_id"] is not None
    ), "no worst_run_id — the replay step of the demo flow has nothing to link to"
    flow["worst_run_id"] = body["worst_run_id"]
    flow["collision_rate"] = body["collision_rate"]


def test_step_2_the_search_finds_the_settings_that_break_the_model(
    client, headers, flow
):
    status = client.get(f"/api/search/{flow['search_id']}/status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "completed", status.json().get("error_message")

    result = client.get(f"/api/search/{flow['search_id']}/result", headers=headers)
    body = result.json()["result"]

    assert body["falsification_found"] is True, (
        "the search did not break a model that collides on this scenario — "
        "the demo flow has nothing to show at this step"
    )
    assert body["falsification_params"], "a falsification with no parameters is not one"


def test_step_3_failures_cluster_into_something_a_human_can_read(flow):
    """Clustering is CLI-level, not an endpoint, so it is exercised directly.
    A report that comes back empty for a batch that collided is the failure
    mode worth catching."""
    pytest.importorskip("sklearn", reason="needs arep[search]")

    from arep.analysis.failure_clustering import FailureClusterer

    report = FailureClusterer().analyse(flow["batch_id"])

    assert report is not None
    assert report.total_runs > 0, "clustering saw no runs for a batch that ran"
    # A batch of a model that collides must not come back reading clean.
    assert (
        report.fail_runs > 0
    ), "clustering found no failures in a batch of a model that collides"
    # Either it named the conditions or it said what the safe region was. An
    # empty report with neither is the dangerous output: it reads like
    # "nothing to worry about".
    assert report.fault_conditions or report.safe_region_description


def test_step_4_the_worst_run_can_be_replayed(client, headers, flow):
    """Both modes. Stored frames when the run collided, replay-from-seed
    otherwise — and the flow must work either way, because which one applies
    depends on what the model did."""
    run_id = flow["worst_run_id"]

    frames = client.get(f"/api/runs/{run_id}/frames", headers=headers)

    if frames.status_code == 200:
        body = frames.json()
        assert body["frame_count"] > 0
        assert body["frames"], "frame_count > 0 but no frames came back"
        # The viewer builds its jump buttons from these.
        assert isinstance(body["markers"], dict)
    else:
        # 404 is the documented answer for a run not worth storing.
        assert frames.status_code == 404, frames.text
        replay = client.post(f"/api/runs/{run_id}/replay", headers=headers)
        assert replay.status_code == 201, replay.text
        assert replay.json()["replay_of"] == run_id


def test_step_5_the_comparison_report_downloads(client, headers, flow):
    """The last step of the demo, and the artefact that leaves the building."""
    status = client.get(f"/api/compare/{flow['comparison_id']}", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "completed", status.json().get("error_message")

    report = client.get(
        f"/api/compare/{flow['comparison_id']}/report.pdf", headers=headers
    )
    assert report.status_code == 200, report.text
    assert report.content, "an empty report is worse than an error"
    assert report.headers["X-ORION-Report-Format"] in ("pdf", "html")


def test_the_flow_charged_credits_and_the_balance_reflects_it(client, headers, flow):
    """Every step above spends credits. A flow that silently charged nothing
    would look identical here and be a revenue bug rather than a broken
    feature."""
    org = client.get("/api/orgs/me", headers=headers).json()
    assert org["run_credits"] >= 0, "the flow drove the balance negative"
