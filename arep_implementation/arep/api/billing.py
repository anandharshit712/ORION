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
from arep.database.repository import OrganisationRepository
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


@billing_router.post("/webhook", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Beta: 200 no-op. Live: verify signature and handle invoice.paid /
    subscription.updated / subscription.deleted. Must be idempotent.
    """
    cfg = get_config()
    if not cfg.billing.billing_enabled:
        logger.debug("Stripe webhook received in beta mode -- ignoring")
        return {"status": "beta_noop"}

    # TODO: payload = await request.body()
    # TODO: event = stripe.Webhook.construct_event(
    #     payload, stripe_signature, cfg.billing.stripe_webhook_secret
    # )
    # TODO: handle event.type:
    #   "invoice.paid"           -> add PLAN_CREDITS[org.plan] to org.run_credits
    #   "subscription.updated"   -> update org.plan
    #   "subscription.deleted"   -> org.plan = "free"
    # TODO: store event.id to deduplicate replays
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
