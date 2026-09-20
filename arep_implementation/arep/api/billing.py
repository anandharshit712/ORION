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
    "beta":        -1,
    "free":        50,
    "starter":    500,
    "pro":      3_000,
    "enterprise":  -1,
}

PLAN_PRICES: dict[str, Optional[str]] = {
    "free":       None,
    "starter":    "price_starter_monthly",   # TODO: real Stripe price ID
    "pro":        "price_pro_monthly",        # TODO: real Stripe price ID
    "enterprise": None,
}

TOPUP_PRICE_ID   = "price_topup_100_runs"    # TODO: real Stripe price ID
TOPUP_CREDITS    = 100
TOPUP_AMOUNT_USD = 10_00                     # $10.00 in cents


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
    billing_active: bool


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
        unlimited = (credits == -1)

    return BillingStatusResponse(
        plan=plan,
        run_credits=credits if not unlimited else 999_999_999,
        credits_unlimited=unlimited,
        next_renewal=None,
        billing_active=cfg.billing.billing_enabled,
    )


@billing_router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(req: CheckoutRequest, request: Request):
    """Beta: 503. Live: create Stripe Checkout session for new subscription."""
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()
    # TODO: stripe.checkout.Session.create(mode="subscription", ...)
    raise NotImplementedError("Set billing_enabled=true and implement Stripe checkout")


@billing_router.post("/topup", response_model=CheckoutResponse)
def create_topup_session(req: TopUpRequest, request: Request):
    """Beta: 503. Live: create Stripe one-time payment for run-credit top-up."""
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()
    # TODO: stripe one-time payment session
    raise NotImplementedError("Set billing_enabled=true and implement Stripe top-up")


@billing_router.get("/portal")
def billing_portal(request: Request):
    """Beta: 503. Live: redirect to Stripe Customer Portal."""
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        raise _billing_disabled_error()
    # TODO: stripe.billing_portal.Session.create(customer=org.stripe_customer_id)
    raise NotImplementedError("Set billing_enabled=true and implement Stripe portal")


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
    except ValueError as exc:                        # unparseable body
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

    with session_scope() as session:
        repo = WebhookEventRepository(session)
        if not repo.claim(event_id, provider="stripe", event_type=event_type):
            logger.info("Stripe webhook %s (%s) already processed -- replay ignored",
                        event_id, event_type)
            return {"status": "duplicate", "event_id": event_id}

        if not cfg.billing.billing_enabled:
            # Beta has no credits to move, so the handler's contract for this
            # event is "do nothing" — and it discharged it. Marking it processed
            # in the same transaction as the claim is the honest record, and it
            # makes replay suppression observable in the mode we actually run in.
            # Stripe's retry window is hours, so nothing pending here survives
            # to the day billing goes live.
            repo.mark_processed(event_id)
            logger.info("Stripe webhook %s (%s) verified in beta mode -- no action",
                        event_id, event_type)
            return {"status": "beta_noop", "event_id": event_id}

    # TODO (Phase 1.4): handle event_type
    #   "invoice.paid"           -> add PLAN_CREDITS[org.plan] to org.run_credits
    #   "subscription.updated"   -> update org.plan
    #   "subscription.deleted"   -> org.plan = "free"
    # then, inside the same transaction as the credit change:
    #   WebhookEventRepository(session).mark_processed(event_id)
    raise NotImplementedError("Set billing_enabled=true and implement Stripe webhook")


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
                    + ("Contact the admin to top up your beta credit pool."
                       if not live else
                       "Please top up via /api/billing/topup.")
                ),
            )


def refund_credits(org_id: str, amount: int) -> None:
    """Refund credits on task failure so crashed runs don't consume credits."""
    with session_scope() as session:
        OrganisationRepository(session).add_credits(org_id, amount)
    logger.info("Refunded %d credits to org=%s", amount, org_id)
