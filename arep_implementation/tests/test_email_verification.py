"""
Email verification tests (Phase 0.4, defect D-04).

Covers the roadmap acceptance criterion "unverified account → POST /api/runs/
returns 403 with a clear message", and the rules around it: an unverified user
can still sign in and read, the token is single-use and expires, and the resend
endpoint cannot be used to discover which addresses hold accounts.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


@pytest.fixture
def sent_links(monkeypatch):
    """Capture verification links instead of mailing them.

    _send_verification imports the sender inside the function body, so patching
    the module attribute is enough — no import-order juggling.
    """
    captured: list[tuple[str, str]] = []

    def fake_send(to_email: str, link: str) -> None:
        captured.append((to_email, link))

    monkeypatch.setattr("arep.api.email_sender.send_verification_email", fake_send)
    return captured


def _signup(client, email: str, username: str) -> dict:
    r = client.post("/api/auth/signup", json={
        "email": email,
        "username": username,
        "password": "correct-horse-battery",
        "org_name": f"{username} Org",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, email: str) -> str:
    r = client.post("/api/auth/login", json={
        "identifier": email, "password": "correct-horse-battery",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token_from(link: str) -> str:
    return link.split("token=", 1)[1]


# -- Signup leaves the address unverified ---------------------------------

def test_signup_creates_an_unverified_user(client, sent_links):
    body = _signup(client, "unverified@example.com", "unverified")
    assert body["email_verified"] is False


def test_signup_sends_exactly_one_link(client, sent_links):
    _signup(client, "onelink@example.com", "onelink")
    assert len(sent_links) == 1
    to_email, link = sent_links[0]
    assert to_email == "onelink@example.com"
    assert "verify-email?token=" in link


def test_unverified_user_can_still_log_in(client, sent_links):
    """D-04 says look around, not locked out — the dashboard must not be a wall."""
    _signup(client, "canlogin@example.com", "canlogin")
    token = _login(client, "canlogin@example.com")
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200


def test_unverified_user_can_read(client, sent_links):
    _signup(client, "canread@example.com", "canread")
    token = _login(client, "canread@example.com")
    assert client.get("/scenarios/", headers=_auth(token)).status_code == 200
    assert client.get("/jobs/", headers=_auth(token)).status_code == 200


# -- The gate (the acceptance criterion) ----------------------------------

def test_unverified_start_run_is_403_with_a_clear_message(client, sent_links):
    """The D-04 acceptance criterion."""
    _signup(client, "norun@example.com", "norun")
    token = _login(client, "norun@example.com")

    r = client.post("/api/runs/", headers=_auth(token), json={
        "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
        "model_name": "EmergencyBrake",
        "master_seed": 42,
    })
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert "not verified" in detail.lower()
    assert "resend-verification" in detail, "the message must say how to fix it"


def test_unverified_cannot_enqueue_a_batch(client, sent_links):
    _signup(client, "nobatch@example.com", "nobatch")
    token = _login(client, "nobatch@example.com")
    r = client.post("/api/runs/batch", headers=_auth(token), json={
        "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
        "model_name": "EmergencyBrake", "num_runs": 2, "master_seed": 1,
    })
    assert r.status_code == 403


def test_unverified_cannot_mint_an_api_key(client, sent_links):
    """Otherwise the gate is one POST away from being bypassed forever."""
    _signup(client, "nokey@example.com", "nokey")
    token = _login(client, "nokey@example.com")
    r = client.post("/api/keys/", headers=_auth(token), json={"label": "sneaky"})
    assert r.status_code == 403


def test_unverified_cannot_register_a_model(client, sent_links):
    _signup(client, "nomodel@example.com", "nomodel")
    token = _login(client, "nomodel@example.com")
    r = client.post("/api/models/register", headers=_auth(token), json={
        "name": "m", "version": "v1", "image_uri": "example.com/m:v1",
    })
    assert r.status_code == 403


def test_unverified_evaluate_is_blocked(client, sent_links):
    _signup(client, "noeval@example.com", "noeval")
    token = _login(client, "noeval@example.com")
    r = client.post("/evaluate/single", headers=_auth(token), json={
        "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
        "model_name": "EmergencyBrake", "master_seed": 1,
    })
    assert r.status_code == 403


# -- Verifying opens the gate ---------------------------------------------

def test_verifying_unlocks_the_blocked_routes(client, sent_links):
    _signup(client, "willverify@example.com", "willverify")
    _, link = sent_links[-1]

    r = client.post("/api/auth/verify-email", json={"token": _token_from(link)})
    assert r.status_code == 200

    token = _login(client, "willverify@example.com")
    assert client.get("/api/auth/me", headers=_auth(token)).json()["email_verified"] is True
    # API key creation was 403 before verifying; it must work now.
    assert client.post("/api/keys/", headers=_auth(token),
                       json={"label": "legit"}).status_code == 201


def test_verification_token_is_single_use(client, sent_links):
    """A link can sit in a browser history or a forwarded mail forever."""
    _signup(client, "singleuse@example.com", "singleuse")
    _, link = sent_links[-1]
    raw = _token_from(link)

    assert client.post("/api/auth/verify-email", json={"token": raw}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"token": raw}).status_code == 400


def test_unknown_token_is_rejected(client):
    r = client.post("/api/auth/verify-email", json={"token": "0" * 64})
    assert r.status_code == 400
    assert "Invalid or expired" in r.json()["detail"]


def test_expired_token_is_rejected(client, sent_links):
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord

    _signup(client, "expired@example.com", "expired")
    _, link = sent_links[-1]

    # Age the send timestamp past the 24h TTL.
    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email="expired@example.com").first()
        user.verification_sent_at = dt.datetime.utcnow() - dt.timedelta(hours=48)

    r = client.post("/api/auth/verify-email", json={"token": _token_from(link)})
    assert r.status_code == 400
    assert "Invalid or expired" in r.json()["detail"]


def test_only_the_hash_is_stored(client, sent_links):
    """A database read must not yield anything replayable as a link."""
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord

    _signup(client, "hashonly@example.com", "hashonly")
    _, link = sent_links[-1]
    raw = _token_from(link)

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email="hashonly@example.com").first()
        assert user.verification_token_hash != raw
        assert len(user.verification_token_hash) == 64


# -- Resend does not leak who has an account ------------------------------

def test_resend_answers_identically_for_unknown_addresses(client, sent_links):
    known = client.post("/api/auth/resend-verification",
                        json={"email": "unverified@example.com"})
    unknown = client.post("/api/auth/resend-verification",
                          json={"email": "nobody-at-all@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_resend_answers_identically_for_verified_addresses(client, sent_links):
    _signup(client, "already@example.com", "already")
    _, link = sent_links[-1]
    client.post("/api/auth/verify-email", json={"token": _token_from(link)})

    before = len(sent_links)
    r = client.post("/api/auth/resend-verification", json={"email": "already@example.com"})
    assert r.status_code == 200
    assert len(sent_links) == before, "a verified address must not be re-mailed"


def test_resend_issues_a_working_new_token(client, sent_links):
    _signup(client, "resend@example.com", "resend")
    first_token = _token_from(sent_links[-1][1])

    # Clear the throttle window so the resend is allowed.
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord
    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email="resend@example.com").first()
        user.verification_sent_at = dt.datetime.utcnow() - dt.timedelta(hours=2)

    client.post("/api/auth/resend-verification", json={"email": "resend@example.com"})
    second_token = _token_from(sent_links[-1][1])
    assert second_token != first_token

    # The replaced token must be dead, and the new one must work.
    assert client.post("/api/auth/verify-email",
                       json={"token": first_token}).status_code == 400
    assert client.post("/api/auth/verify-email",
                       json={"token": second_token}).status_code == 200


def test_resend_is_throttled_per_user(client, sent_links):
    """Per-IP limits do not stop someone mailbombing one address."""
    _signup(client, "throttle@example.com", "throttle")
    before = len(sent_links)

    for _ in range(3):
        r = client.post("/api/auth/resend-verification",
                        json={"email": "throttle@example.com"})
        assert r.status_code == 200          # never reveals the throttle

    assert len(sent_links) == before, "signup just mailed; resends must be held back"
