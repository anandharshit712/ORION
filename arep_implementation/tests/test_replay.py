"""
Deterministic replay (Phase 2.5).

Replay is the proof of the determinism claim, so the test that matters is the
frame hash: re-running a stored run's `(scenario, model, seed)` must produce the
same digest it produced the first time. If it does not, either determinism is
broken or replay is not replaying the same thing, and both are worse than having
no replay at all.

The second thing pinned here is *which* scenario gets replayed. The stored YAML
is used, never the file at the original path: scenario files get edited -- the
lane-geometry correction moved every score in the library -- and a replay that
quietly runs a different scenario looks authoritative while being wrong.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

SCENARIO = "scenarios/basic/straight_road_lead_vehicle.yaml"
PARAMETERISED = "../scenarios/lon/LON-003_emergency_stop.yaml"


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
def account(client):
    """One shared account: signup is rate limited to 3/hour/IP."""
    email = "replay@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "replayer",
            "password": "password123",
            "org_name": "replay org",
            "org_slug": "replay",
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


def _await_run(client, headers, run_id, timeout_s=45.0):
    """Poll GET /api/runs/{id} until the run leaves the running state."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"/api/runs/{run_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("complete", "completed", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish within {timeout_s}s")


def _stored_run(org_id, *, seed=42, yaml_content=None):
    """Run a real simulation and persist it, the way the batch path does."""
    from arep.database.connection import session_scope
    from arep.database.repository import RunRepository, ScenarioRepository
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel
    from arep.scenario.parser import ScenarioParser

    result = EvaluationRunner().run_single(
        SCENARIO, EmergencyBrakeModel(), master_seed=seed
    )
    scenario_def, content_hash = ScenarioParser().parse_file(SCENARIO)

    with open(SCENARIO, encoding="utf-8") as fh:
        stored_yaml = yaml_content if yaml_content is not None else fh.read()

    with session_scope() as db:
        rec = ScenarioRepository(db).upsert(
            name=scenario_def.name,
            version=scenario_def.version,
            content_hash=content_hash if yaml_content is None else "e" * 64,
            yaml_content=stored_yaml,
            duration=scenario_def.duration,
            road_type=scenario_def.road.road_type,
            num_traffic_objects=len(scenario_def.traffic_objects),
        )
        run = RunRepository(db).save_result(rec.id, result, org_id=org_id)
        db.flush()
        return run.id, result


# -- The determinism claim -------------------------------------------------


def test_running_the_same_seed_twice_gives_the_same_frame_hash():
    """The guarantee replay rests on, checked without the API in the way."""
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    first = EvaluationRunner().run_single(
        SCENARIO, EmergencyBrakeModel(), master_seed=7
    )
    second = EvaluationRunner().run_single(
        SCENARIO, EmergencyBrakeModel(), master_seed=7
    )

    assert first.frame_hash, "no digest was recorded"
    assert first.frame_hash == second.frame_hash


def test_a_different_seed_gives_a_different_hash_when_the_scenario_is_parameterised():
    """Otherwise the digest proves nothing — a constant would also 'match'.

    Needs a scenario with a `parameterization` block. On an unparameterised one
    the seed has nothing to draw, so the hashes match and *should*.
    """
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    a = EvaluationRunner().run_single(
        PARAMETERISED, EmergencyBrakeModel(), master_seed=1
    )
    b = EvaluationRunner().run_single(
        PARAMETERISED, EmergencyBrakeModel(), master_seed=2
    )
    assert a.frame_hash != b.frame_hash


def test_the_seed_does_not_change_an_unparameterised_scenario():
    """The other half of the same property, stated deliberately: a scenario
    that declares no ranges has nothing to vary, so every seed is the same run.
    Worth pinning, because it otherwise looks like the seed is being ignored."""
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel

    a = EvaluationRunner().run_single(SCENARIO, EmergencyBrakeModel(), master_seed=1)
    b = EvaluationRunner().run_single(SCENARIO, EmergencyBrakeModel(), master_seed=2)
    assert a.frame_hash == b.frame_hash


# -- The endpoint ----------------------------------------------------------


def test_replay_starts_a_run_carrying_the_original_parameters(client, account):
    headers, org_id = account
    run_id, original = _stored_run(org_id, seed=123)

    r = client.post(f"/api/runs/{run_id}/replay", headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()

    assert body["replay_of"] == run_id
    assert body["master_seed"] == 123
    assert body["model_name"] == "EmergencyBrake"
    assert body["ws_url"] == f"/ws/simulation/{body['run_id']}"
    # The digest to compare against is handed back with the replay, so a client
    # does not have to go and fetch the original run to check.
    assert body["original_frame_hash"] == original.frame_hash


def test_the_replay_reproduces_the_original_frame_hash(client, account):
    """The acceptance criterion: replay-from-seed produces an identical hash."""
    headers, org_id = account
    run_id, original = _stored_run(org_id, seed=99)

    r = client.post(f"/api/runs/{run_id}/replay", headers=headers)
    assert r.status_code == 201, r.text
    live_id = r.json()["run_id"]

    # Poll the public endpoint rather than the registry: that is the surface a
    # client verifying a replay actually has, and the registry is async.
    status = _await_run(client, headers, live_id)

    assert status["status"] == "complete", f"replay ended {status['status']}"
    assert status["replay_of"] == run_id
    assert (
        status["frame_hash"] == original.frame_hash
    ), "replay produced a different digest — determinism or replay is broken"


def test_replay_uses_the_stored_yaml_not_the_file_on_disk(client, account):
    """A replay must reproduce the run that happened, not whatever the scenario
    file says today. Storing a deliberately different duration proves which one
    is being read."""
    headers, org_id = account

    with open(SCENARIO, encoding="utf-8") as fh:
        edited = fh.read().replace("duration: 30.0", "duration: 4.0")
    assert "duration: 4.0" in edited, "fixture no longer contains the expected duration"

    run_id, _ = _stored_run(org_id, seed=55, yaml_content=edited)

    r = client.post(f"/api/runs/{run_id}/replay", headers=headers)
    assert r.status_code == 201, r.text

    status = _await_run(client, headers, r.json()["run_id"])
    assert status["status"] == "complete"

    # The edited YAML says 4 s; the file on disk says 30 s. A replay that used
    # the file would produce a completely different digest from this one.
    # sim_time is not on the status response, so compare against a fresh run of
    # the *stored* scenario instead: equal digests prove which YAML was used.
    from arep.execution.runner import EvaluationRunner
    from arep.models.examples.example_models import EmergencyBrakeModel
    from arep.scenario.parser import ScenarioParser

    edited_def, _ = ScenarioParser().parse_string(edited)
    expected = EvaluationRunner().run_scenario_definition(
        edited_def, EmergencyBrakeModel(), 55
    )
    assert (
        status["frame_hash"] == expected.frame_hash
    ), "replay did not reproduce the stored scenario — it used the file on disk"


# -- Access control --------------------------------------------------------


def test_another_orgs_run_cannot_be_replayed(client, account):
    """404, not 403: whether a run id exists is not a stranger's business."""
    headers, _ = account

    # A run belonging to nobody (org_id=None) is not this org's run.
    orphan_id, _ = _stored_run(None, seed=77)

    r = client.post(f"/api/runs/{orphan_id}/replay", headers=headers)
    assert r.status_code == 404


def test_replaying_an_unknown_run_is_a_404(client, account):
    headers, _ = account
    assert client.post("/api/runs/999999/replay", headers=headers).status_code == 404


def test_replay_requires_auth(client):
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.post("/api/runs/1/replay").status_code == 401
