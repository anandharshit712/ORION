"""
Stripe billing tests (Phase 1.4).

Covers the roadmap acceptance criteria:
  - a free-tier org with 0 credits gets 402 on POST /api/runs/batch
  - an upgrade grants the tier's credits
  - a replayed webhook does not double credits (idempotency from 0.3)

Stripe itself is stubbed. These tests are about our side of the contract —
which org an event maps to, what moves credits and what deliberately does not,
and what happens on a replay — none of which needs a network call to verify.
The signature machinery has its own tests in test_webhook_security.py.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

PASSWORD = "correct-horse-battery"
WEBHOOK_SECRET = "whsec_billing_test_secret"


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


@pytest.fixture(autouse=True)
def clean_cookies(client):
    client.cookies.clear()
    yield
    client.cookies.clear()


def _account(client, slug: str) -> dict:
    email = f"{slug}@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": slug,
            "password": PASSWORD,
            "org_name": f"{slug} org",
            "org_slug": slug,
        },
    )
    assert r.status_code == 201, r.text
    verify_email_for(email)
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"identifier": email, "password": PASSWORD})
    client.cookies.clear()
    return {
        "org_id": r.json()["org_id"],
        "headers": {"Authorization": f"Bearer {r.json()['access_token']}"},
    }


@pytest.fixture
def org(client):
    import uuid

    return _account(client, f"bill{uuid.uuid4().hex[:8]}")


@pytest.fixture
def live_billing(monkeypatch):
    """Turn billing on and point the webhook at a known signing secret."""
    from arep.config import get_config, reload_config

    monkeypatch.setenv("AREP_BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
    reload_config()
    yield get_config()
    reload_config()


@pytest.fixture
def fake_stripe(monkeypatch):
    """A stripe double that records what we asked it to create."""
    calls: dict[str, list] = {"customers": [], "checkout": [], "portal": []}

    def customer_create(**kwargs):
        calls["customers"].append(kwargs)
        return types.SimpleNamespace(id=f"cus_test_{len(calls['customers'])}")

    def checkout_create(**kwargs):
        calls["checkout"].append(kwargs)
        return types.SimpleNamespace(url="https://checkout.stripe.test/session")

    def portal_create(**kwargs):
        calls["portal"].append(kwargs)
        return types.SimpleNamespace(url="https://portal.stripe.test/session")

    stub = types.SimpleNamespace(
        api_key=None,
        Customer=types.SimpleNamespace(create=customer_create),
        checkout=types.SimpleNamespace(
            Session=types.SimpleNamespace(create=checkout_create)
        ),
        billing_portal=types.SimpleNamespace(
            Session=types.SimpleNamespace(create=portal_create)
        ),
    )

    from arep.api import billing

    monkeypatch.setattr(billing, "_stripe", lambda: stub)
    return calls


def _credits(client, org) -> int:
    return client.get("/api/orgs/me", headers=org["headers"]).json()["run_credits"]


def _set_plan(org_id: str, plan: str, credits: int) -> None:
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    with session_scope() as session:
        record = OrganisationRepository(session).get_by_id(org_id)
        record.plan = plan
        record.run_credits = credits


# -- Usage ----------------------------------------------------------------


def test_usage_reports_plan_and_credits(client, org):
    r = client.get("/api/billing/usage", headers=org["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["plan"]
    assert "run_credits" in body
    assert body["billing_active"] is False  # beta by default


def test_usage_requires_auth(client):
    assert client.get("/api/billing/usage").status_code == 401


def test_usage_reports_unlimited_without_a_negative_number(client, org):
    """-1 is a sentinel; showing it to a customer as "-1 credits" is nonsense."""
    _set_plan(org["org_id"], "enterprise", -1)
    body = client.get("/api/billing/usage", headers=org["headers"]).json()
    assert body["credits_unlimited"] is True
    assert body["run_credits"] > 0


# -- Beta mode refuses rather than half-works -----------------------------


def test_checkout_is_503_in_beta(client, org):
    r = client.post(
        "/api/billing/checkout",
        headers=org["headers"],
        json={
            "plan": "starter",
            "success_url": "https://x/ok",
            "cancel_url": "https://x/no",
        },
    )
    assert r.status_code == 503


def test_portal_is_503_in_beta(client, org):
    assert client.get("/api/billing/portal", headers=org["headers"]).status_code == 503


# -- Checkout -------------------------------------------------------------


def test_checkout_creates_a_customer_then_a_session(
    client, org, live_billing, fake_stripe
):
    r = client.post(
        "/api/billing/checkout",
        headers=org["headers"],
        json={
            "plan": "starter",
            "success_url": "https://x/ok",
            "cancel_url": "https://x/no",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"].startswith("https://checkout.stripe.test")

    assert len(fake_stripe["customers"]) == 1
    session_kwargs = fake_stripe["checkout"][0]
    assert session_kwargs["mode"] == "subscription"
    assert session_kwargs["metadata"]["org_id"] == org["org_id"]
    assert session_kwargs["metadata"]["plan"] == "starter"


def test_the_customer_is_created_once_and_reused(
    client, org, live_billing, fake_stripe
):
    """A second Stripe customer for one org splits their billing history."""
    body = {
        "plan": "starter",
        "success_url": "https://x/ok",
        "cancel_url": "https://x/no",
    }
    client.post("/api/billing/checkout", headers=org["headers"], json=body)
    client.post("/api/billing/checkout", headers=org["headers"], json=body)
    assert len(fake_stripe["customers"]) == 1


def test_checkout_rejects_an_unknown_plan(client, org, live_billing, fake_stripe):
    r = client.post(
        "/api/billing/checkout",
        headers=org["headers"],
        json={
            "plan": "platinum",
            "success_url": "https://x/ok",
            "cancel_url": "https://x/no",
        },
    )
    assert r.status_code == 400


def test_checkout_rejects_plans_with_no_self_serve_price(
    client, org, live_billing, fake_stripe
):
    """free needs no checkout; enterprise is negotiated."""
    for plan in ("free", "enterprise"):
        r = client.post(
            "/api/billing/checkout",
            headers=org["headers"],
            json={
                "plan": plan,
                "success_url": "https://x/ok",
                "cancel_url": "https://x/no",
            },
        )
        assert r.status_code == 400, plan


def test_portal_refuses_before_any_subscription(client, org, live_billing, fake_stripe):
    """Creating a customer here would leave an empty Stripe record behind."""
    r = client.get("/api/billing/portal", headers=org["headers"])
    assert r.status_code == 409


def test_portal_works_once_a_customer_exists(client, org, live_billing, fake_stripe):
    client.post(
        "/api/billing/checkout",
        headers=org["headers"],
        json={
            "plan": "starter",
            "success_url": "https://x/ok",
            "cancel_url": "https://x/no",
        },
    )
    r = client.get("/api/billing/portal", headers=org["headers"])
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://portal.stripe.test")


# -- Webhooks -------------------------------------------------------------


def _signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    ts = int(time.time())
    digest = hmac.new(
        secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={digest}"


def _event(event_id: str, event_type: str, obj: dict) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "api_version": "2024-06-20",
            "created": int(time.time()),
            "type": event_type,
            "data": {"object": obj},
        }
    ).encode()


def _post_event(client, payload: bytes):
    return client.post(
        "/api/billing/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "stripe-signature": _signature(payload),
        },
    )


def _stripe_customer_for(org_id: str) -> str:
    """Attach a Stripe customer id so webhook lookup can find the org."""
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    customer_id = f"cus_{org_id[:12]}"
    with session_scope() as session:
        OrganisationRepository(session).set_stripe_customer_id(org_id, customer_id)
    return customer_id


def test_invoice_paid_grants_the_plan_credits(client, org, live_billing):
    """The acceptance criterion: an upgrade grants the tier's allocation."""
    _set_plan(org["org_id"], "starter", 0)
    customer = _stripe_customer_for(org["org_id"])

    r = _post_event(
        client,
        _event(
            "evt_inv_1",
            "invoice.paid",
            {"id": "in_1", "object": "invoice", "customer": customer},
        ),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "handled"
    assert _credits(client, org) == 500  # starter allocation


def test_a_replayed_invoice_does_not_double_credits(client, org, live_billing):
    """The 0.3 idempotency ledger, now guarding real money."""
    _set_plan(org["org_id"], "starter", 0)
    customer = _stripe_customer_for(org["org_id"])
    payload = _event(
        "evt_inv_replay",
        "invoice.paid",
        {"id": "in_2", "object": "invoice", "customer": customer},
    )

    assert _post_event(client, payload).status_code == 200
    after_first = _credits(client, org)

    second = _post_event(client, payload)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert _credits(client, org) == after_first


def test_a_topup_invoice_grants_the_packs_bought(client, org, live_billing):
    _set_plan(org["org_id"], "free", 0)
    customer = _stripe_customer_for(org["org_id"])

    r = _post_event(
        client,
        _event(
            "evt_topup_1",
            "invoice.paid",
            {
                "id": "in_3",
                "object": "invoice",
                "customer": customer,
                "metadata": {"topup_credits": "300"},
            },
        ),
    )
    assert r.status_code == 200
    assert _credits(client, org) == 300


def test_subscription_updated_changes_the_plan_but_not_credits(
    client, org, live_billing
):
    """Otherwise every card update would hand out a free month."""
    _set_plan(org["org_id"], "free", 42)
    customer = _stripe_customer_for(org["org_id"])

    r = _post_event(
        client,
        _event(
            "evt_sub_1",
            "customer.subscription.updated",
            {
                "id": "sub_1",
                "object": "subscription",
                "customer": customer,
                "status": "active",
                "current_period_end": int(time.time()) + 30 * 86400,
                "metadata": {"plan": "pro"},
            },
        ),
    )
    assert r.status_code == 200

    body = client.get("/api/billing/usage", headers=org["headers"]).json()
    assert body["plan"] == "pro"
    assert body["subscription_status"] == "active"
    assert body["next_renewal"] is not None
    assert _credits(client, org) == 42, "a plan change must not grant credits"


def test_subscription_deleted_drops_to_free_and_keeps_paid_credits(
    client, org, live_billing
):
    """Credits were paid for; confiscating them takes back delivered value."""
    _set_plan(org["org_id"], "pro", 250)
    customer = _stripe_customer_for(org["org_id"])

    r = _post_event(
        client,
        _event(
            "evt_sub_del",
            "customer.subscription.deleted",
            {
                "id": "sub_2",
                "object": "subscription",
                "customer": customer,
                "status": "canceled",
            },
        ),
    )
    assert r.status_code == 200

    body = client.get("/api/billing/usage", headers=org["headers"]).json()
    assert body["plan"] == "free"
    assert _credits(client, org) == 250


def test_an_unhandled_event_type_is_accepted_not_errored(client, org, live_billing):
    """Stripe sends far more types than we subscribe to."""
    r = _post_event(
        client,
        _event("evt_other", "charge.succeeded", {"id": "ch_1", "object": "charge"}),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ignored"


def test_an_event_for_an_unknown_customer_is_not_an_error(client, live_billing):
    """A webhook for an org that was deleted must not wedge Stripe's retries."""
    r = _post_event(
        client,
        _event(
            "evt_unknown",
            "invoice.paid",
            {
                "id": "in_x",
                "object": "invoice",
                "customer": "cus_does_not_exist",
            },
        ),
    )
    assert r.status_code == 200


# -- Credit enforcement ---------------------------------------------------


def test_a_free_org_with_no_credits_gets_402_on_batch(client, org):
    """The acceptance criterion."""
    _set_plan(org["org_id"], "free", 0)

    r = client.post(
        "/api/runs/batch",
        headers=org["headers"],
        json={
            "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
            "model_name": "EmergencyBrake",
            "num_runs": 1,
            "master_seed": 1,
        },
    )
    assert r.status_code == 402


def test_an_org_cannot_start_more_runs_than_it_has_credits(client, org):
    _set_plan(org["org_id"], "free", 2)
    r = client.post(
        "/api/runs/batch",
        headers=org["headers"],
        json={
            "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
            "model_name": "EmergencyBrake",
            "num_runs": 5,
            "master_seed": 2,
        },
    )
    assert r.status_code == 402
    assert _credits(client, org) == 2, "a refused batch must not spend anything"


def test_unlimited_credits_can_actually_run(client, org):
    """-1 means unlimited, but the plain `<` comparison in deduct_credits read
    it as "less than any amount" and refused every run."""
    _set_plan(org["org_id"], "enterprise", -1)

    r = client.post(
        "/api/runs/batch",
        headers=org["headers"],
        json={
            "scenario_path": "scenarios/basic/straight_road_lead_vehicle.yaml",
            "model_name": "EmergencyBrake",
            "num_runs": 2,
            "master_seed": 3,
        },
    )
    assert r.status_code == 202, r.text

    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    with session_scope() as session:
        assert (
            OrganisationRepository(session).get_by_id(org["org_id"]).run_credits == -1
        ), "unlimited must stay unlimited"
