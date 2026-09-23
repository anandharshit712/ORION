"""
Model version history (Phase 3.4).

`models.version` has been a column with an index since P1.2, but nothing read
it, so "version history shows the correct trend across 3 submissions" could not
be checked at all.

The acceptance criterion is the trend, so that is what these pin: three
submissions of the same name, scored differently, must come back oldest-first
with deltas against the previous version and a regression flagged where one
happened.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

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


@pytest.fixture(scope="module")
def account(client):
    email = "history@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "historian",
            "password": "password123",
            "org_name": "history org",
            "org_slug": "history",
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


def _submit_version(org_id, name, version, *, composites=(), created_offset=0):
    """Register a model version and give it scored runs.

    Runs reference a submitted model by its UUID, which is the indirection the
    history endpoint has to walk.
    """
    import datetime

    from arep.database.connection import session_scope
    from arep.database.models import ModelRecord, RunRecord, ScenarioRecord

    model_id = str(uuid.uuid4())
    with session_scope() as db:
        db.add(
            ModelRecord(
                id=model_id,
                org_id=org_id,
                name=name,
                version=version,
                submission_type="docker",
                artefact_uri=f"registry.test/{name}:{version}",
                status="ready",
                created_at=datetime.datetime(2026, 1, 1)
                + datetime.timedelta(days=created_offset),
            )
        )

        scenario = (
            db.query(ScenarioRecord)
            .filter(ScenarioRecord.content_hash == "h" * 64)
            .first()
        )
        if scenario is None:
            scenario = ScenarioRecord(
                name="history scenario",
                version="1.0",
                content_hash="h" * 64,
                yaml_content="scenario: {}",
                duration=20.0,
                road_type="highway",
                num_traffic_objects=1,
            )
            db.add(scenario)
            db.flush()

        for i, composite in enumerate(composites):
            db.add(
                RunRecord(
                    org_id=org_id,
                    scenario_id=scenario.id,
                    model_name=model_id,  # the UUID, not the name
                    master_seed=i,
                    duration=20.0,
                    termination_reason="timeout",
                    composite_score=composite,
                    safety_score=composite,
                    compliance_score=composite,
                    stability_score=composite,
                    reactivity_score=composite,
                    collision_occurred=composite < 0.3,
                    min_ttc=8.0,
                )
            )
    return model_id


# -- The trend -------------------------------------------------------------


def test_three_submissions_show_the_trend_oldest_first(client, account):
    """The acceptance criterion."""
    headers, org_id = account
    _submit_version(org_id, "planner", "v1", composites=(0.70, 0.72), created_offset=0)
    _submit_version(org_id, "planner", "v2", composites=(0.80, 0.82), created_offset=1)
    _submit_version(org_id, "planner", "v3", composites=(0.90, 0.88), created_offset=2)

    r = client.get("/api/models/planner/history", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    versions = body["versions"]
    assert [v["version"] for v in versions] == ["v1", "v2", "v3"], "a trend reads forwards"
    assert body["latest_version"] == "v3"

    assert versions[0]["composite_mean"] == pytest.approx(0.71)
    assert versions[0]["composite_delta"] is None, "the first version has no baseline"
    assert versions[1]["composite_delta"] == pytest.approx(0.10, abs=1e-6)
    assert versions[2]["composite_delta"] == pytest.approx(0.08, abs=1e-6)

    assert not body["has_regression"], "every version improved"


def test_a_regression_between_versions_is_flagged(client, account):
    headers, org_id = account
    _submit_version(org_id, "drifter", "v1", composites=(0.90,), created_offset=0)
    _submit_version(org_id, "drifter", "v2", composites=(0.60,), created_offset=1)

    body = client.get("/api/models/drifter/history", headers=headers).json()

    assert body["versions"][1]["composite_delta"] == pytest.approx(-0.30)
    assert body["versions"][1]["is_regression"] is True
    assert body["has_regression"] is True


def test_a_small_dip_is_not_a_regression(client, account):
    """The threshold is shared with RegressionDetector, so the dashboard and the
    CLI cannot disagree about what counts."""
    headers, org_id = account
    _submit_version(org_id, "steady", "v1", composites=(0.90,), created_offset=0)
    _submit_version(org_id, "steady", "v2", composites=(0.895,), created_offset=1)

    body = client.get("/api/models/steady/history", headers=headers).json()
    assert body["versions"][1]["is_regression"] is False
    assert body["has_regression"] is False


# -- Honest edges ----------------------------------------------------------


def test_an_unevaluated_version_is_listed_not_hidden(client, account):
    """"Uploaded but never run" is a real state. Hiding it would make a
    submission look lost."""
    headers, org_id = account
    _submit_version(org_id, "unrun", "v1", composites=(), created_offset=0)

    body = client.get("/api/models/unrun/history", headers=headers).json()
    entry = body["versions"][0]

    assert entry["runs"] == 0
    assert entry["composite_mean"] is None
    assert entry["composite_delta"] is None


def test_an_unevaluated_version_does_not_break_the_chain(client, account):
    """A version with no runs must not reset the baseline, or the next real
    version looks like the first one and its regression goes unreported."""
    headers, org_id = account
    _submit_version(org_id, "gappy", "v1", composites=(0.90,), created_offset=0)
    _submit_version(org_id, "gappy", "v2", composites=(), created_offset=1)
    _submit_version(org_id, "gappy", "v3", composites=(0.50,), created_offset=2)

    body = client.get("/api/models/gappy/history", headers=headers).json()
    v3 = body["versions"][2]

    assert v3["composite_delta"] == pytest.approx(-0.40), "compared against v1, not nothing"
    assert v3["is_regression"] is True


def test_an_unknown_model_name_is_a_404(client, account):
    headers, _ = account
    assert client.get("/api/models/nope/history", headers=headers).status_code == 404


def test_another_orgs_model_is_not_visible(client, account):
    headers, _ = account
    _submit_version("some-other-org", "secret", "v1", composites=(0.9,))

    assert client.get("/api/models/secret/history", headers=headers).status_code == 404


def test_history_requires_auth(client):
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/models/planner/history").status_code == 401
