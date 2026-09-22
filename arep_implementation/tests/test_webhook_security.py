"""
Webhook signature verification and replay suppression (Phase 0.3).

Covers the roadmap acceptance criterion "a replayed webhook event id is a
no-op", plus the signature checks that make the criterion meaningful — replay
suppression on an endpoint anyone can post to is not a security control.

The side effects themselves land in Phase 1.4. What is tested here is the
envelope: who is allowed to be heard, and how often the same thing counts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEBHOOK_SECRET = "whsec_test_secret_for_signature_verification"


@pytest.fixture(scope="module")
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{path}"

    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{path}")

    yield path

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def signed_client(db_path):
    """App with a webhook signing secret configured, billing still in beta.

    Beta plus a secret is the state this phase actually ships: signatures are
    verified and events deduplicated before there is any money to move, so the
    wiring is exercised ahead of 1.4 rather than alongside it.
    """
    from arep.config import reload_config

    os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    reload_config()

    from fastapi.testclient import TestClient
    from arep.api.app import create_app

    with TestClient(create_app()) as c:
        yield c

    del os.environ["STRIPE_WEBHOOK_SECRET"]
    reload_config()


@pytest.fixture
def unsigned_client(db_path):
    """App in beta with no signing secret — the local-development default."""
    from arep.config import reload_config

    os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
    reload_config()

    from fastapi.testclient import TestClient
    from arep.api.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _stripe_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a valid Stripe-Signature header.

    Stripe signs the string "<timestamp>.<raw body>" with HMAC-SHA256 and sends
    it as "t=<timestamp>,v1=<hex digest>". Reproducing that here (rather than
    mocking the verifier away) is what makes these tests prove the real library
    call accepts our good cases and rejects the bad ones.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _event(event_id: str, event_type: str = "invoice.paid") -> bytes:
    """A minimally realistic Stripe event envelope.

    "object": "event" is required — stripe's construct_event reads it while
    converting the payload, and a fixture without it fails inside the library
    rather than in our code.
    """
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "api_version": "2024-06-20",
            "created": int(time.time()),
            "type": event_type,
            "data": {
                "object": {"id": "in_test", "object": "invoice", "amount_paid": 4900}
            },
        }
    ).encode()


def _post(client, payload: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["stripe-signature"] = signature
    return client.post("/api/billing/webhook", content=payload, headers=headers)


# -- Signature verification -----------------------------------------------


def test_valid_signature_is_accepted(signed_client):
    payload = _event("evt_valid_001")
    r = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
    assert r.status_code == 200


def test_missing_signature_is_rejected(signed_client):
    """The endpoint is unauthenticated by necessity; the signature is the auth."""
    r = _post(signed_client, _event("evt_nosig_001"), None)
    assert r.status_code == 400
    assert "signature" in r.json()["detail"].lower()


def test_forged_signature_is_rejected(signed_client):
    """Anyone can post here. A wrong key must not grant credits."""
    payload = _event("evt_forged_001")
    forged = _stripe_signature(payload, "whsec_attacker_guess")
    r = _post(signed_client, payload, forged)
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid webhook signature"


def test_tampered_payload_is_rejected(signed_client):
    """Sign one body, send another: the HMAC covers the bytes, not the id."""
    signature = _stripe_signature(_event("evt_original"), WEBHOOK_SECRET)
    r = _post(signed_client, _event("evt_swapped"), signature)
    assert r.status_code == 400


def test_stale_timestamp_is_rejected(signed_client):
    """Stripe's tolerance window — a captured request cannot be replayed later."""
    payload = _event("evt_stale_001")
    old = _stripe_signature(
        payload, WEBHOOK_SECRET, timestamp=int(time.time()) - 86_400
    )
    r = _post(signed_client, payload, old)
    assert r.status_code == 400


def test_garbage_body_with_valid_signature_is_rejected(signed_client):
    """A correctly signed non-JSON body still must not reach the handler."""
    payload = b"this is not json"
    r = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
    assert r.status_code == 400


# -- Replay suppression (the acceptance criterion) ------------------------


def test_replayed_event_id_is_a_noop(signed_client):
    """The D-03 acceptance criterion.

    Both deliveries are individually valid — same id, freshly signed, exactly
    as Stripe retries. The second must not be handled again.
    """
    payload = _event("evt_replay_001")

    first = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
    assert first.status_code == 200

    second = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


def test_duplicate_returns_200_not_an_error(signed_client):
    """Stripe retries on any non-2xx, so answering 409 would cause a retry storm."""
    payload = _event("evt_replay_002")
    for _ in range(3):
        r = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
        assert r.status_code == 200


def test_distinct_event_ids_are_each_processed(signed_client):
    """Dedup must key on the event id, not on the payload shape or the route."""
    for n in range(3):
        payload = _event(f"evt_distinct_{n}")
        r = _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))
        assert r.json().get("status") != "duplicate"


def test_event_is_recorded_in_the_ledger(signed_client):
    from arep.database.connection import session_scope
    from arep.database.repository import WebhookEventRepository

    payload = _event("evt_ledger_001", event_type="customer.subscription.updated")
    _post(signed_client, payload, _stripe_signature(payload, WEBHOOK_SECRET))

    with session_scope() as session:
        record = WebhookEventRepository(session).get("evt_ledger_001")
        assert record is not None
        assert record.provider == "stripe"
        assert record.event_type == "customer.subscription.updated"


# -- The ledger's crash semantics -----------------------------------------


def test_unfinished_events_stay_claimable(db_path):
    """A handler that died mid-flight must not swallow the retry.

    The row is left at "received", meaning the side effect may never have been
    applied — dropping the retry there loses the event outright, which is worse
    than a handler running twice.
    """
    from arep.database.connection import session_scope
    from arep.database.repository import WebhookEventRepository

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        assert repo.claim("evt_crash_001") is True  # first delivery
        assert repo.claim("evt_crash_001") is True  # retry after a crash

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        repo.mark_processed("evt_crash_001")

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        assert repo.claim("evt_crash_001") is False  # now it is settled


def test_mark_processed_stamps_a_time(db_path):
    from arep.database.connection import session_scope
    from arep.database.repository import WebhookEventRepository

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        repo.claim("evt_stamp_001")
        assert repo.get("evt_stamp_001").processed_at is None

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        repo.mark_processed("evt_stamp_001")

    with session_scope() as session:
        record = WebhookEventRepository(session).get("evt_stamp_001")
        assert record.status == "processed"
        assert record.processed_at is not None


def test_provider_is_recorded_but_is_not_part_of_the_key(db_path):
    """event_id alone identifies a delivery; provider only labels it.

    Provider event ids are unique within a provider and prefixed by it in
    practice, so a composite key would guarantee against a collision that
    cannot occur. Keeping the key single-column keeps claim() a single lookup.
    """
    from arep.database.connection import session_scope
    from arep.database.repository import WebhookEventRepository

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        assert repo.claim("evt_provider_001", provider="stripe") is True
        repo.mark_processed("evt_provider_001")

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        assert repo.get("evt_provider_001").provider == "stripe"
        assert repo.claim("evt_provider_001", provider="paddle") is False


# -- Beta behaviour -------------------------------------------------------


def test_beta_without_a_secret_still_accepts_and_drops(unsigned_client):
    """Local development must not require Stripe setup to boot."""
    r = _post(unsigned_client, _event("evt_beta_001"), None)
    assert r.status_code == 200
    assert r.json()["status"] == "beta_noop"


def test_beta_with_a_secret_enforces_it(signed_client):
    """Configuring a secret opts into verification even before going live."""
    r = _post(signed_client, _event("evt_beta_002"), None)
    assert r.status_code == 400
