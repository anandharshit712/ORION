"""
WebSocket ticket authentication tests (Phase 0.4, defect D-04).

Covers the roadmap acceptance criterion "WS connect with an expired or reused
ticket → 4401 close; JWT never in the WS URL".

The happy-path stream still lives in scripts/ws_smoke.py against a real uvicorn
server — TestClient does not reliably drive a long-lived producer task in the
same event loop, which is why that script exists. What is pinned here is the
part that has to be right: who gets in.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

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


@pytest.fixture(autouse=True)
def clean_tickets():
    from arep.api.ws_tickets import clear_tickets

    clear_tickets()
    yield
    clear_tickets()


@pytest.fixture(scope="module")
def token(client):
    email = "ws-ticket@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "wsticket",
            "password": "correct-horse-battery",
            "org_name": "WS Ticket Org",
        },
    )
    assert r.status_code == 201, r.text
    verify_email_for(email)
    r = client.post(
        "/api/auth/login",
        json={
            "identifier": email,
            "password": "correct-horse-battery",
        },
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# -- Ticket lifecycle -----------------------------------------------------


def test_ticket_is_single_use():
    """The whole point: a URL captured from a log must not reconnect."""
    from arep.api.ws_tickets import issue_ticket, redeem_ticket

    ticket, _ = issue_ticket("run-1", user_id=7, org_id="org-a")
    assert redeem_ticket(ticket, "run-1") == (7, "org-a")
    assert redeem_ticket(ticket, "run-1") is None


def test_ticket_expires():
    from arep.api import ws_tickets

    ticket, ttl = ws_tickets.issue_ticket("run-2", user_id=7, org_id="org-a")
    assert ttl == int(ws_tickets.TICKET_TTL_SECONDS)

    # Age it past its window rather than sleeping a minute in a unit test.
    ws_tickets._tickets[ticket].expires_at = time.monotonic() - 1
    assert ws_tickets.redeem_ticket(ticket, "run-2") is None


def test_ticket_is_bound_to_one_run():
    """A ticket for a run you own must not open a socket onto another."""
    from arep.api.ws_tickets import issue_ticket, redeem_ticket

    ticket, _ = issue_ticket("run-mine", user_id=7, org_id="org-a")
    assert redeem_ticket(ticket, "run-someone-elses") is None
    # And it is spent — a wrong-run attempt does not get a second try.
    assert redeem_ticket(ticket, "run-mine") is None


def test_unknown_ticket_is_rejected():
    from arep.api.ws_tickets import redeem_ticket

    assert redeem_ticket("not-a-real-ticket", "run-1") is None


def test_expired_tickets_are_pruned_on_issue():
    """The store must not grow without bound across a long-lived process."""
    from arep.api import ws_tickets

    stale, _ = ws_tickets.issue_ticket("run-old", user_id=1, org_id="org-a")
    ws_tickets._tickets[stale].expires_at = time.monotonic() - 1

    ws_tickets.issue_ticket("run-new", user_id=1, org_id="org-a")
    assert stale not in ws_tickets._tickets


# -- The minting endpoint -------------------------------------------------


def test_ticket_endpoint_requires_auth(client):
    assert client.post("/api/runs/does-not-exist/ws-ticket").status_code == 401


def test_ticket_endpoint_404s_for_an_unknown_run(client, token):
    r = client.post("/api/runs/no-such-run/ws-ticket", headers=_auth(token))
    assert r.status_code == 404


def test_ticket_endpoint_404s_rather_than_403_for_another_orgs_run(client, token):
    """A 403 would confirm the run exists somewhere else."""
    import asyncio

    from arep.api.sim_registry import LiveRun, get_registry

    foreign = LiveRun(
        run_id="foreign-run",
        scenario_path="x",
        scenario_name="x",
        model_name="EmergencyBrake",
        master_seed=1,
        status="running",
        started_at="2026-09-20T00:00:00Z",
        org_id="some-other-org",
    )
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        get_registry().register(foreign)
    )

    r = client.post("/api/runs/foreign-run/ws-ticket", headers=_auth(token))
    assert r.status_code == 404


# -- The socket itself ----------------------------------------------------


def test_ws_without_a_ticket_is_refused(client):
    """The query parameter is required, so the handshake fails outright."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect("/ws/simulation/any-run"):
            pass


def test_ws_with_a_bad_ticket_closes_4401(client):
    """The D-04 acceptance criterion: 4401, not a generic policy close."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/simulation/any-run?ticket=garbage") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4401


def test_ws_with_a_reused_ticket_closes_4401(client):
    """Redeeming happens before anything else, so a replay never reaches a run."""
    from starlette.websockets import WebSocketDisconnect

    from arep.api.ws_tickets import issue_ticket, redeem_ticket

    ticket, _ = issue_ticket("run-x", user_id=1, org_id="org-a")
    redeem_ticket(ticket, "run-x")  # first use, elsewhere

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(f"/ws/simulation/run-x?ticket={ticket}") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4401


def test_jwt_is_not_accepted_as_a_ws_credential(client, token):
    """The old ?token= path must be gone, not merely discouraged."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises((WebSocketDisconnect, Exception)):
        with client.websocket_connect(f"/ws/simulation/any-run?token={token}"):
            pass


def test_ws_url_from_the_endpoint_carries_no_jwt(client, token):
    """Whatever the client is handed must not embed the session credential."""
    import asyncio

    from arep.api.sim_registry import LiveRun, get_registry

    org_id = client.get("/api/auth/me", headers=_auth(token)).json()["org_id"]
    run = LiveRun(
        run_id="own-run",
        scenario_path="x",
        scenario_name="x",
        model_name="EmergencyBrake",
        master_seed=1,
        status="running",
        started_at="2026-09-20T00:00:00Z",
        org_id=org_id,
    )
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        get_registry().register(run)
    )

    r = client.post("/api/runs/own-run/ws-ticket", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "ticket=" in body["ws_url"]
    assert "token=" not in body["ws_url"]
    assert token not in body["ws_url"]
    assert body["expires_in"] == 60
