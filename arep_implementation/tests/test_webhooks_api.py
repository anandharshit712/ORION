"""
Webhook registration and dispatch over HTTP (Phase 3.1).

The SSRF controls are tested in `test_webhook_safety.py`. What is pinned here is
that the API refuses a dangerous URL at registration, never hands a secret back
twice, keeps one org's endpoints invisible to another, and — the one that costs
money if it is wrong — never lets a customer's broken endpoint fail the run that
triggered the notification.
"""

from __future__ import annotations

import os
import socket
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


@pytest.fixture(scope="module")
def account(client):
    """One shared account — signup is rate limited to 3/hour/IP."""
    email = "hooks@example.com"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "hooker",
            "password": "password123",
            "org_name": "hook org",
            "org_slug": "hooks",
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


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Resolve everything to a public address unless a test says otherwise, so
    these tests never touch the network."""

    def fake(hostname, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def _register(client, headers, url="https://hooks.example.com/orion", events=None):
    return client.post(
        "/api/webhooks/",
        headers=headers,
        json={"url": url, "events": events or ["batch.completed"]},
    )


# -- Registration ----------------------------------------------------------


def test_registering_returns_the_secret_exactly_once(client, account):
    """Same contract as an API key: shown at creation, never retrievable after.
    A secret a customer can fetch again is one an attacker can fetch too."""
    headers, _ = account

    created = _register(client, headers)
    assert created.status_code == 201, created.text
    assert created.json()["secret"], "the secret must be returned on creation"

    listed = client.get("/api/webhooks/", headers=headers).json()
    assert listed
    assert all(h["secret"] is None for h in listed), "secrets must never be listed"


def test_a_dangerous_url_is_refused_at_registration(client, account, monkeypatch):
    """Rejecting at registration is a courtesy, not the control — delivery
    re-validates — but a customer should learn immediately, not silently never
    receive anything."""
    headers, _ = account

    def metadata(hostname, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", metadata)

    r = _register(client, headers, url="http://metadata.example.com/hook")
    assert r.status_code == 400
    assert "rejected" in r.json()["detail"].lower()


def test_an_unknown_event_is_rejected_not_ignored(client, account):
    """A typo that silently never fires is worse than an error: the customer
    waits for a call that will never come."""
    headers, _ = account

    r = _register(client, headers, events=["batch.complete"])  # missing 'd'
    assert r.status_code == 400
    assert "batch.complete" in r.json()["detail"]


def test_a_supplied_secret_is_honoured(client, account):
    headers, _ = account
    r = client.post(
        "/api/webhooks/",
        headers=headers,
        json={
            "url": "https://hooks.example.com/mine",
            "events": ["run.completed"],
            "secret": "a-secret-long-enough-to-be-real",
        },
    )
    assert r.status_code == 201
    assert r.json()["secret"] == "a-secret-long-enough-to-be-real"


def test_the_per_org_limit_is_enforced(client, account):
    """Few enough that a compromised account cannot turn ORION into a fan-out
    amplifier.

    Cleans up after itself: filling the quota and leaving it full would make
    every later registration in this module fail for the wrong reason.
    """
    from arep.api.webhooks import MAX_WEBHOOKS_PER_ORG

    headers, _ = account
    created: list[int] = []
    try:
        for i in range(MAX_WEBHOOKS_PER_ORG + 2):
            r = _register(client, headers, url=f"https://hooks.example.com/limit{i}")
            if r.status_code == 400:
                assert "limit" in r.json()["detail"].lower()
                break
            created.append(r.json()["id"])
        else:
            pytest.fail("the per-org webhook limit was never enforced")
    finally:
        for webhook_id in created:
            client.delete(f"/api/webhooks/{webhook_id}", headers=headers)


# -- Dispatch --------------------------------------------------------------


def test_dispatch_records_the_outcome_without_the_body(client, account, monkeypatch):
    """Storing a response body would turn a webhook into a way to read whatever
    the URL pointed at."""
    from arep.api import webhook_delivery, webhooks

    headers, org_id = account
    created = _register(client, headers, url="https://hooks.example.com/record")
    webhook_id = created.json()["id"]

    monkeypatch.setattr(
        webhook_delivery,
        "deliver",
        lambda **kw: webhook_delivery.DeliveryOutcome(
            delivered=True, status_code=200, duration_ms=12
        ),
    )

    assert webhooks.dispatch("batch.completed", org_id, {"batch_id": 7}) >= 1

    rows = client.get(f"/api/webhooks/{webhook_id}/deliveries", headers=headers).json()
    assert rows
    assert rows[0]["delivered"] is True
    assert rows[0]["status_code"] == 200
    assert "body" not in rows[0]


def test_a_broken_endpoint_never_raises_into_the_caller(client, account, monkeypatch):
    """The caller is a worker finishing a batch. A customer's dead endpoint must
    not fail the run they paid for."""
    from arep.api import webhook_delivery, webhooks

    headers, org_id = account
    _register(client, headers, url="https://hooks.example.com/broken")

    def explode(**kwargs):
        raise RuntimeError("endpoint is on fire")

    monkeypatch.setattr(webhook_delivery, "deliver", explode)

    # Must return, not raise.
    assert webhooks.dispatch("batch.completed", org_id, {"batch_id": 1}) == 0


def test_repeated_failures_disable_the_endpoint(client, account, monkeypatch):
    """Retrying an address nobody is listening at forever costs worker time and
    achieves nothing. Disabled rather than deleted, so the customer can see why
    and re-enable it."""
    from arep.api import webhook_delivery, webhooks
    from arep.api.webhooks import MAX_CONSECUTIVE_FAILURES

    headers, org_id = account
    created = _register(client, headers, url="https://hooks.example.com/dead")
    webhook_id = created.json()["id"]

    monkeypatch.setattr(
        webhook_delivery,
        "deliver",
        lambda **kw: webhook_delivery.DeliveryOutcome(
            delivered=False, error="unreachable"
        ),
    )

    for _ in range(MAX_CONSECUTIVE_FAILURES + 1):
        webhooks.dispatch("batch.completed", org_id, {})

    hooks = client.get("/api/webhooks/", headers=headers).json()
    dead = next(h for h in hooks if h["id"] == webhook_id)
    assert dead["active"] is False


def test_only_subscribed_events_are_delivered(client, account, monkeypatch):
    from arep.api import webhook_delivery, webhooks

    headers, org_id = account
    _register(
        client,
        headers,
        url="https://hooks.example.com/only-runs",
        events=["run.completed"],
    )

    sent = []
    monkeypatch.setattr(
        webhook_delivery,
        "deliver",
        lambda **kw: (
            sent.append(kw["event"]),
            webhook_delivery.DeliveryOutcome(delivered=True, status_code=200),
        )[1],
    )

    webhooks.dispatch("search.completed", org_id, {})
    assert "search.completed" not in sent


def test_dispatch_with_no_org_does_nothing(monkeypatch):
    """A run with no org - a local CLI invocation - has nobody to notify."""
    from arep.api import webhooks

    assert webhooks.dispatch("batch.completed", None, {}) == 0


# -- Tenancy ---------------------------------------------------------------


def test_another_orgs_webhook_is_invisible(client, account):
    headers, _ = account
    created = _register(client, headers, url="https://hooks.example.com/mine-only")
    webhook_id = created.json()["id"]

    from arep.database.connection import session_scope
    from arep.database.models import WebhookRecord

    with session_scope() as db:
        db.get(WebhookRecord, webhook_id).org_id = "someone-else"

    assert (
        client.get(
            f"/api/webhooks/{webhook_id}/deliveries", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/webhooks/{webhook_id}", headers=headers).status_code == 404
    )


def test_webhook_endpoints_require_auth(client):
    from fastapi.testclient import TestClient

    with TestClient(client.app) as anonymous:
        assert anonymous.get("/api/webhooks/").status_code == 401
        assert anonymous.post("/api/webhooks/", json={}).status_code == 401
