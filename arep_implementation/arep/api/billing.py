"""
ORION Billing.

Two modes controlled by config.billing.billing_enabled:

  False (beta/testing mode — default):
    - GET  /api/billing/usage     -> real credit data from DB, plan shown as "beta"
    - POST /api/billing/checkout  -> 503 with a clear "billing not active" message
    - POST /api/billing/topup     -> 503 with a clear "billing not active" message
    - GET  /api/billing/portal    -> 503 with a clear "billing not active" message
    - POST /api/billing/webhook   -> 200 no-op (Stripe won't call this in beta anyway)
    - Credit deduction + refund work normally -- the system is fully exercised

  True (live mode -- set AREP_BILLING_ENABLED=true + Stripe env vars):
    - All routes are fully implemented via Stripe Checkout / webhooks
    - Flip the flag and fill in the TODO blocks below -- zero structural changes needed

To go live:
  1. AREP_BILLING_ENABLED=true
  2. STRIPE_SECRET_KEY=sk_live_...
  3. STRIPE_WEBHOOK_SECRET=whsec_...
  4. Replace placeholder price IDs in PLAN_PRICES / TOPUP_PRICE_ID with real values
"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal
from arep.config import get_config
from arep.database.connection import session_scope
from arep.database.repository import OrganisationRepository, WebhookEventRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.billing")

billing_router = APIRouter(prefix="/api/billing", tags=["Billing"])

# Plan definitions
PLAN_CREDITS: dict[str, int] = {
    "beta": -1,
    "free": 50,
    "starter": 500,
    "pro": 3_000,
    "enterprise": -1,
}

PLAN_PRICES: dict[str, Optional[str]] = {
    "free": None,
    "starter": "price_starter_monthly",  # TODO: real Stripe price ID
    "pro": "price_pro_monthly",  # TODO: real Stripe price ID
    "enterprise": None,
}

PLAN_MONTHLY_USD: dict[str, Optional[int]] = {
    "free": 0,
    "starter": 49,
    "pro": 199,
    "enterprise": None,  # negotiated
}

TOPUP_PRICE_ID = "price_topup_100_runs"  # TODO: real Stripe price ID
TOPUP_CREDITS = 100
TOPUP_AMOUNT_USD = 10_00  # $10.00 in cents


def _billing_disabled_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Billing is not active in this environment. "
            "The platform is currently in beta -- contact the admin to adjust your credits."
        ),
    )


class CheckoutRequest(BaseModel):
    plan: str = Field(..., description="starter | pro | enterprise")
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class TopUpRequest(BaseModel):
    quantity: int = Field(1, ge=1, description="Number of 100-credit packs")
    success_url: str
    cancel_url: str


class BillingStatusResponse(BaseModel):
    plan: str
    run_credits: int
    credits_unlimited: bool
    next_renewal: Optional[str]
    # None in beta and for orgs that never subscribed. "past_due" still has
    # access while Stripe retries; "canceled" does not.
    subscription_status: Optional[str] = None
    billing_active: bool


class PlanResponse(BaseModel):
    name: str
    monthly_usd: Optional[int]
    run_credits: int
    credits_unlimited: bool
    self_serve: bool


@billing_router.get("/plans", response_model=list[PlanResponse])
def list_plans():
    """The plan catalogue, so the frontend never hardcodes an allocation.

    Public: these are published prices, and the pricing page needs them before
    anyone has an account. It also stops the numbers drifting — the billing page
    previously advertised 100/2,500/15,000 credits against the real
    50/500/3,000, which is the kind of mismatch a customer notices on their
    first invoice.
    """
    return [
        PlanResponse(
            name=name,
            monthly_usd=PLAN_MONTHLY_USD.get(name),
            run_credits=credits if credits >= 0 else 0,
            credits_unlimited=credits < 0,
            self_serve=PLAN_PRICES.get(name) is not None,
        )
        for name, credits in PLAN_CREDITS.items()
        if name != "beta"  # internal state, not a purchasable plan
    ]


@billing_router.get("/usage", response_model=BillingStatusResponse)
def get_billing_status(request: Request):
    """Return current plan, credits remaining, and billing status. Works in both modes."""
    cfg = get_config()
    org_id, _, _ = get_request_principal(request)

    with session_scope() as session:
        org = OrganisationRepository(session).get_by_id(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organisation not found")
        plan = org.plan if org.plan else "beta"
        credits = org.run_credits
        unlimited = credits == -1
        period_end = org.current_period_end
        status = org.subscription_status

    return BillingStatusResponse(
        plan=plan,
        run_credits=credits if not unlimited else 999_999_999,
        credits_unlimited=unlimited,
        next_renewal=period_end.isoformat() if period_end else None,
        subscription_status=status,
        billing_active=cfg.billing.billing_enabled,
    )


def _stripe():
    """Configured stripe module.

    Imported and keyed here rather than at module import time so the API still
    boots with no Stripe credentials — which is the beta configuration, and the
    one every test runs under.
    """
    import stripe

    stripe.api_key = get_config().billing.stripe_secret_key
    return stripe


def _ensure_customer(org_id: str) -> str:
    """Return this org's Stripe customer id, creating one on first use.

    Created lazily rather than at signup: an org that never pays should not
    exist in Stripe at all, and signup must not fail because Stripe is down.
    """
    with session_scope() as session:
        repo = OrganisationRepository(session)
        org = repo.get_by_id(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organisation not found")
        if org.stripe_customer_id:
            return org.stripe_customer_id
        org_name, org_slug = org.name, org.slug

    customer = _stripe().Customer.create(
        name=org_name,
        metadata={"org_id": org_id, "org_slug": org_slug},
    )

    with session_scope() as session:
        OrganisationRepository(session).set_stripe_customer_id(org_id, customer.id)
    logger.info("Created Stripe customer for org=%s", org_id)
    return customer.id


@billing_router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(req: CheckoutRequest, request: Request):
    """Start a hosted Checkout session for a subscription.

    Stripe-hosted: no card details ever reach this server, which keeps the PCI
    scope to "we redirect to Stripe".
    """
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()

    org_id, _, _ = get_request_principal(request)

    price_id = PLAN_PRICES.get(req.plan)
    if req.plan not in PLAN_CREDITS:
        raise HTTPException(status_code=400, detail=f"Unknown plan {req.plan!r}")
    if price_id is None:
        # free and enterprise have no self-serve price: one needs no checkout,
        # the other is negotiated.
        raise HTTPException(
            status_code=400,
            detail=f"Plan {req.plan!r} is not available through self-serve checkout",
        )

    customer_id = _ensure_customer(org_id)
    session_obj = _stripe().checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        # Echoed back on the webhook, so the handler can cross-check the org
        # rather than trusting the customer lookup alone.
        metadata={"org_id": org_id, "plan": req.plan},
    )
    logger.info("Checkout session created for org=%s plan=%s", org_id, req.plan)
    return CheckoutResponse(checkout_url=session_obj.url)


@billing_router.post("/topup", response_model=CheckoutResponse)
def create_topup_session(req: TopUpRequest, request: Request):
    """One-off credit purchase, outside the subscription."""
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()

    org_id, _, _ = get_request_principal(request)
    customer_id = _ensure_customer(org_id)

    session_obj = _stripe().checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[{"price": TOPUP_PRICE_ID, "quantity": req.quantity}],
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        metadata={
            "org_id": org_id,
            "topup_credits": str(TOPUP_CREDITS * req.quantity),
        },
    )
    logger.info("Top-up session created for org=%s packs=%d", org_id, req.quantity)
    return CheckoutResponse(checkout_url=session_obj.url)


@billing_router.get("/portal", response_model=CheckoutResponse)
def billing_portal(request: Request, return_url: Optional[str] = None):
    """Hand the customer to Stripe's portal to manage their own subscription.

    Cancellation, card updates and invoice history all live there, so none of
    it needs building or securing here.
    """
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()

    org_id, _, _ = get_request_principal(request)

    with session_scope() as session:
        org = OrganisationRepository(session).get_by_id(org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Organisation not found")
        customer_id = org.stripe_customer_id

    if not customer_id:
        # No customer means they have never checked out; there is nothing to
        # manage, and creating one here would leave an empty Stripe record.
        raise HTTPException(
            status_code=409,
            detail="No subscription to manage. Start a plan first.",
        )

    # Stripe requires a return_url. Default to the app's own billing page so a
    # caller that omits it still lands somewhere sensible.
    from arep.config.env import get_settings

    portal = _stripe().billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url or f"{get_settings().public_url}/billing",
    )
    return CheckoutResponse(checkout_url=portal.url)


def verify_stripe_signature(payload: bytes, signature_header: Optional[str]):
    """
    Verify a Stripe webhook signature and return the decoded event.

    This endpoint is unauthenticated by necessity — Stripe cannot hold one of our
    tokens — so the signature IS the authentication. Anything reaching the
    handler body without passing through here is an anonymous stranger posting
    JSON at a route that grants credits.

    ``stripe.Webhook.construct_event`` checks the HMAC and the timestamp
    tolerance (replay window) in one call; hand-rolling the scheme would be more
    code with more ways to get constant-time comparison wrong.

    Raises:
        HTTPException: 400 on a missing, malformed or invalid signature.
        HTTPException: 503 when live billing is on but no signing secret is set —
            a misconfiguration, not a caller error, and the one case where
            failing open would be silently unsafe.
    """
    import stripe

    secret = get_config().billing.stripe_webhook_secret
    if not secret:
        logger.error("Stripe webhook received but stripe_webhook_secret is unset")
        raise HTTPException(
            status_code=503,
            detail="Webhook signing secret is not configured",
        )

    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        return stripe.Webhook.construct_event(payload, signature_header, secret)
    except ValueError as exc:  # unparseable body
        logger.warning("Stripe webhook payload rejected: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook payload")
    except stripe.error.SignatureVerificationError as exc:
        logger.warning("Stripe webhook signature rejected: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")


@billing_router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Inbound Stripe webhook.

    Signature verification and replay suppression are live in both modes; only
    the per-event side effects wait for 1.4. That ordering is deliberate: they
    are the parts that are dangerous to bolt onto a money path afterwards.

    Flow: verify signature -> claim the event id -> handle -> mark processed.
    A replayed event id that already reached ``processed`` returns 200 without
    re-running anything, because a retried ``invoice.paid`` would otherwise
    grant the credits twice. Stripe retries on any non-2xx, so a duplicate must
    answer 200, not an error.
    """
    cfg = get_config()
    payload = await request.body()

    # In beta with no secret configured, Stripe is not sending anything real —
    # accept and drop, which keeps local development free of Stripe setup. With
    # a secret present we verify even in beta, so the wiring is exercised before
    # it guards real money.
    if not cfg.billing.billing_enabled and not cfg.billing.stripe_webhook_secret:
        logger.debug("Stripe webhook received in beta mode with no secret -- ignoring")
        return {"status": "beta_noop"}

    event = verify_stripe_signature(payload, stripe_signature)

    # construct_event returns a StripeObject, which exposes fields as attributes
    # and has no dict .get() in stripe >= 15 — reading it like a dict raises
    # AttributeError at runtime, not at import.
    event_id = getattr(event, "id", None)
    event_type = getattr(event, "type", None)
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook event has no id")
    if not event_type:
        raise HTTPException(status_code=400, detail="Webhook event has no type")

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        if not repo.claim(event_id, provider="stripe", event_type=event_type):
            logger.info(
                "Stripe webhook %s (%s) already processed -- replay ignored",
                event_id,
                event_type,
            )
            return {"status": "duplicate", "event_id": event_id}

        if not cfg.billing.billing_enabled:
            # Beta has no credits to move, so the handler's contract for this
            # event is "do nothing" — and it discharged it. Marking it processed
            # in the same transaction as the claim is the honest record, and it
            # makes replay suppression observable in the mode we actually run in.
            # Stripe's retry window is hours, so nothing pending here survives
            # to the day billing goes live.
            repo.mark_processed(event_id)
            logger.info(
                "Stripe webhook %s (%s) verified in beta mode -- no action",
                event_id,
                event_type,
            )
            return {"status": "beta_noop", "event_id": event_id}

    handler = _EVENT_HANDLERS.get(event_type)
    if handler is None:
        # Stripe sends far more event types than we subscribe to, and an
        # unhandled one is not an error. Marked processed so a retry of
        # something we will never act on stops arriving.
        with session_scope() as session:
            WebhookEventRepository(session).mark_processed(event_id)
        logger.info("Stripe webhook %s (%s) not handled here", event_id, event_type)
        return {"status": "ignored", "event_id": event_id}

    try:
        handler(event)
    except Exception:
        # Left unprocessed on purpose: the claim row stays at "received", so
        # Stripe's retry is allowed through and can complete the work. Answer
        # non-2xx so a retry actually happens.
        logger.exception("Stripe webhook %s (%s) handler failed", event_id, event_type)
        raise HTTPException(status_code=500, detail="Webhook handler failed")

    with session_scope() as session:
        WebhookEventRepository(session).mark_processed(event_id)

    logger.info("Stripe webhook %s (%s) handled", event_id, event_type)
    return {"status": "handled", "event_id": event_id}


# ── Webhook handlers (Phase 1.4) ─────────────────────────────────────────


def _metadata_value(obj, key: str) -> Optional[str]:
    """Read one metadata key off a Stripe object.

    StripeObject has no dict ``.get()`` in stripe >= 15 — the same trap that
    made ``event.get("id")`` raise AttributeError. A ``hasattr(x, "get")`` guard
    does not help: it is simply False, so the lookup silently yields None and
    the caller quietly takes the wrong branch. Subscript first, attribute
    second, so both StripeObject and a plain dict work.
    """
    metadata = getattr(obj, "metadata", None)
    if metadata is None:
        return None
    try:
        value = metadata[key]
    except (KeyError, TypeError, AttributeError):
        value = getattr(metadata, key, None)
    return str(value) if value is not None else None


def _org_for_event(obj) -> Optional[str]:
    """Resolve the org an event is about.

    Prefers the org_id we put in metadata at checkout, and falls back to the
    Stripe customer id. Metadata is more direct, but it is only present on
    objects that originated from our own checkout call — a subscription renewed
    a year later carries only the customer.
    """
    org_id = _metadata_value(obj, "org_id")
    if org_id:
        return org_id

    customer_id = getattr(obj, "customer", None)
    if not customer_id:
        return None
    with session_scope() as session:
        org = OrganisationRepository(session).get_by_stripe_customer_id(
            str(customer_id)
        )
        return org.id if org else None


def _period_end(obj) -> Optional[datetime.datetime]:
    raw = getattr(obj, "current_period_end", None)
    if not raw:
        return None
    return datetime.datetime.utcfromtimestamp(int(raw))


def _handle_invoice_paid(event) -> None:
    """Money arrived: grant the period's credits.

    Credits are granted here and nowhere else. Doing it on
    subscription.updated would hand out a month of runs every time someone
    changed their card.
    """
    invoice = event["data"]["object"]
    org_id = _org_for_event(invoice)
    if org_id is None:
        logger.warning("invoice.paid for an unknown customer — ignoring")
        return

    topup = _metadata_value(invoice, "topup_credits")

    with session_scope() as session:
        repo = OrganisationRepository(session)
        org = repo.get_by_id(org_id)
        if org is None:
            logger.warning("invoice.paid for org=%s which no longer exists", org_id)
            return

        if topup:
            amount = int(topup)
            reason = "top-up"
        else:
            amount = PLAN_CREDITS.get(org.plan, 0)
            reason = f"plan {org.plan}"
            if amount < 0:
                # Unlimited plan: nothing to grant.
                logger.info("invoice.paid for unlimited org=%s — no grant", org_id)
                return

        repo.add_credits(org_id, amount)
        logger.info("Granted %d credits to org=%s (%s)", amount, org_id, reason)


def _plan_from_subscription(subscription) -> Optional[str]:
    """Map a Stripe subscription back to one of our plan names.

    Checks the checkout metadata first, then the price id, because a
    subscription created through the Stripe dashboard has no metadata of ours.
    """
    plan = _metadata_value(subscription, "plan")
    if plan in PLAN_CREDITS:
        return plan

    try:
        price_id = subscription["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    for name, configured in PLAN_PRICES.items():
        if configured and configured == price_id:
            return name
    return None


def _handle_subscription_updated(event) -> None:
    """Plan or status changed. Does not touch credits — see _handle_invoice_paid."""
    subscription = event["data"]["object"]
    org_id = _org_for_event(subscription)
    if org_id is None:
        logger.warning("subscription.updated for an unknown customer — ignoring")
        return

    plan = _plan_from_subscription(subscription)
    if plan is None:
        logger.warning(
            "subscription.updated for org=%s with an unrecognised price", org_id
        )
        return

    with session_scope() as session:
        OrganisationRepository(session).apply_subscription(
            org_id,
            plan=plan,
            subscription_id=getattr(subscription, "id", None),
            status=getattr(subscription, "status", None),
            current_period_end=_period_end(subscription),
        )
    logger.info("org=%s now on plan=%s", org_id, plan)


def _handle_subscription_deleted(event) -> None:
    """Subscription ended: drop to free.

    Existing credits are deliberately left alone. They were paid for, and
    confiscating them on cancellation would be taking back delivered value.
    """
    subscription = event["data"]["object"]
    org_id = _org_for_event(subscription)
    if org_id is None:
        logger.warning("subscription.deleted for an unknown customer — ignoring")
        return

    with session_scope() as session:
        OrganisationRepository(session).apply_subscription(
            org_id,
            plan="free",
            status=getattr(subscription, "status", "canceled"),
        )
    logger.info("org=%s subscription ended, dropped to free", org_id)


_EVENT_HANDLERS = {
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_succeeded": _handle_invoice_paid,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.created": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


def deduct_credits(org_id: str, amount: int) -> None:
    """
    Atomically deduct run credits. Raises 402 if insufficient.
    Works in both beta and live mode.
    """
    with session_scope() as session:
        success = OrganisationRepository(session).deduct_credits(org_id, amount)
        if not success:
            live = get_config().billing.billing_enabled
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Insufficient run credits (tried to use {amount}). "
                    + (
                        "Contact the admin to top up your beta credit pool."
                        if not live
                        else "Please top up via /api/billing/topup."
                    )
                ),
            )


def refund_credits(org_id: str, amount: int) -> None:
    """Refund credits on task failure so crashed runs don't consume credits."""
    with session_scope() as session:
        OrganisationRepository(session).add_credits(org_id, amount)
    logger.info("Refunded %d credits to org=%s", amount, org_id)
