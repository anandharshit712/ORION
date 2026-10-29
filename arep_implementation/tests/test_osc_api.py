"""
OpenSCENARIO 2.0 import / export endpoints (Phase 4.4).

Export reads a library scenario by id; import parses and validates an uploaded
file and hands the result back without storing it. Both sit behind router
auth like every other data route.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.api.osc_routes import MAX_OSC_BYTES  # noqa: E402
from arep.scenario.osc_importer import OpenSCENARIOImporter  # noqa: E402
from arep.scenario.parser import ScenarioParser  # noqa: E402

TESTS = Path(__file__).resolve().parent
FIXTURE = TESTS / "fixtures" / "osc" / "cut_in_hand_authored.osc"
LON003 = TESTS.parent.parent / "scenarios" / "lon" / "LON-003_emergency_stop.yaml"


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
def auth(client):
    r = client.post(
        "/api/auth/signup",
        json={
            "email": "osc-test@example.com",
            "username": "osctest",
            "password": "correct-horse-battery",
            "org_name": "OSC Test Org",
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/api/auth/login",
        json={
            "identifier": "osc-test@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert r.status_code == 200, r.text
    client.cookies.clear()  # Bearer only, so the anonymous tests stay anonymous
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _import(client, auth, body):
    return client.post(
        "/api/scenarios/import/osc",
        content=body,
        headers={**auth, "Content-Type": "text/plain"},
    )


# -- Export ---------------------------------------------------------------


def test_export_requires_auth(client):
    r = client.get("/api/scenarios/LON-003/export/osc")
    assert r.status_code == 401


def test_export_returns_osc_that_re_imports(client, auth):
    r = client.get("/api/scenarios/LON-003/export/osc", headers=auth)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    assert 'filename="LON-003.osc"' in r.headers["content-disposition"]

    original, _ = ScenarioParser().parse_file(LON003)
    imported, skipped = OpenSCENARIOImporter().read(r.text)
    assert skipped == []
    assert dataclasses.asdict(imported) == dataclasses.asdict(original)


@pytest.mark.parametrize(
    "scenario_id, status",
    [("lon-003", 400), ("LON-3", 400), ("ZZZ-999", 404), ("EMG-004", 422)],
)
def test_export_errors(client, auth, scenario_id, status):
    r = client.get(f"/api/scenarios/{scenario_id}/export/osc", headers=auth)
    assert r.status_code == status
    assert "detail" in r.json()


# -- Import ---------------------------------------------------------------


def test_import_requires_auth(client):
    r = client.post("/api/scenarios/import/osc", content="scenario t:\n")
    assert r.status_code == 401


def test_import_reports_what_it_skipped(client, auth):
    r = _import(client, auth, FIXTURE.read_bytes())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["validation_errors"] == []
    assert any("change_lane" in line for line in body["skipped"])
    assert body["scenario"]["scenario"]["name"] == "cut_in_hand_authored"


def test_imported_scenario_is_a_loadable_scenario_file(client, auth):
    """The response is the YAML shape, complete enough to save and run."""
    osc = client.get("/api/scenarios/LON-003/export/osc", headers=auth).text
    body = _import(client, auth, osc.encode("utf-8")).json()
    assert body["skipped"] == []

    reparsed, _ = ScenarioParser().parse_string(yaml.safe_dump(body["scenario"]))
    original, _ = ScenarioParser().parse_file(LON003)
    assert dataclasses.asdict(reparsed) == dataclasses.asdict(original)


def test_import_without_a_scenario_is_a_400(client, auth):
    r = _import(client, auth, b"ego: Vehicle\n")
    assert r.status_code == 400
    assert "declares no scenario" in r.json()["detail"]


def test_import_that_fails_validation_says_so(client, auth):
    r = _import(client, auth, b"scenario t:\n    do parallel(duration: -1s):\n")
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["validation_errors"]


def test_import_is_size_bounded(client, auth):
    r = _import(client, auth, b"#" * (MAX_OSC_BYTES + 1))
    assert r.status_code == 413
    assert "detail" in r.json()


def test_import_rejects_non_utf8(client, auth):
    r = _import(client, auth, b"scenario t:\n\xff\xfe\n")
    assert r.status_code == 400
