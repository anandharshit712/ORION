"""
ORION Billing.  [Phase 1]

Stripe integration for subscription management and credit top-ups.

Responsibilities:
  - Create Stripe Checkout sessions (new subscription or top-up)
  - Handle incoming Stripe webhooks (invoice.paid, subscription.updated, etc.)
  - Deduct and refund run credits atomically
  - Expose billing status to the dashboard

Stripe library is loaded lazily — not installed in dev environments
that don't need billing.

Plan → credit mapping:
  free       →    50 credits / month
  starter    →   500 credits / month
  pro        → 3,000 credits / month
  enterprise → unlimited (stored as -1)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from arep.utils.logging_config import get_logger

logger = get_logger("api.billing")

billing_router = APIRouter(prefix="/api/billing", tags=["Billing"])

# ── Plan definitions ──────────────────────────────────────────────────────

PLAN_CREDITS: dict[str, int] = {
    "free": 50,
    "starter": 500,
    "pro": 3_000,
    "enterprise": -1,        # -1 = unlimited
}

PLAN_PRICES: dict[str, Optional[str]] = {
    "free": None,            # No Stripe price ID
    "starter": "price_starter_monthly",    # TODO [P1]: replace with real Stripe price IDs
    "pro": "price_pro_monthly",
    "enterprise": None,      # Custom — handled via Stripe quote
}

TOPUP_PRICE_ID = "price_topup_100_runs"   # TODO [P1]: replace with real Stripe price ID
TOPUP_CREDITS = 100
TOPUP_AMOUNT_USD = 10_00    # $10.00 in cents


# ── Request/response schemas ──────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str                # "starter" | "pro" | "enterprise"
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class TopUpRequest(BaseModel):
    quantity: int = 1        # number of 100-credit packs
    success_url: str
    cancel_url: str


class BillingStatusResponse(BaseModel):
    plan: str
    run_credits: int
    next_renewal: Optional[str]
    stripe_customer_id: Optional[str]


# ── Routes ────────────────────────────────────────────────────────────────

@billing_router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """
    Create a Stripe Checkout session for a new subscription.

    TODO [P1]: Import stripe, call stripe.checkout.Session.create()
    TODO [P1]: Attach org_id as metadata so webhook can identify the customer
    TODO [P1]: Return session URL to redirect the user
    """
    raise NotImplementedError("Stripe checkout not yet implemented")


@billing_router.post("/topup", response_model=CheckoutResponse)
async def create_topup_session(req: TopUpRequest, request: Request):
    """
    Create a Stripe Checkout session for a run-credit top-up purchase.

    TODO [P1]: Create one-time payment session for req.quantity * TOPUP_CREDITS
    """
    raise NotImplementedError("Stripe top-up not yet implemented")


@billing_router.get("/portal")
async def billing_portal(request: Request):
    """
    Redirect to Stripe Customer Portal for self-service billing management.

    TODO [P1]: Look up org's stripe_customer_id, create portal session, return URL
    """
    raise NotImplementedError("Stripe portal not yet implemented")


@billing_router.get("/usage", response_model=BillingStatusResponse)
async def get_billing_status(request: Request):
    """
    Return current plan, credits remaining, and next renewal date.

    TODO [P1]: Read from organisations table via org_id from request.state
    """
    raise NotImplementedError("Billing status not yet implemented")


@billing_router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Handle incoming Stripe webhook events.

    Events handled:
      invoice.paid             → top up run_credits by plan allocation
      subscription.updated     → update org.plan
      subscription.deleted     → downgrade org to free plan

    IMPORTANT: This endpoint must be idempotent.
    Use Stripe's event ID to deduplicate — replay a webhook twice should
    not double-credit an org.

    TODO [P1]: Verify webhook signature with stripe.Webhook.construct_event()
    TODO [P1]: Handle invoice.paid → credit org
    TODO [P1]: Handle subscription.updated → update org.plan
    TODO [P1]: Store event ID in webhook_deliveries table to ensure idempotency
    """
    raise NotImplementedError("Stripe webhook handler not yet implemented")


# ── Credit management helpers ─────────────────────────────────────────────

def deduct_credits(org_id: str, amount: int) -> None:
    """
    Atomically deduct `amount` run credits from an org.

    Uses SELECT FOR UPDATE to prevent race conditions under concurrent requests.
    Raises HTTPException(402) if insufficient credits.

    TODO [P1]: Implement with session_scope() + SELECT FOR UPDATE
    """
    raise NotImplementedError("deduct_credits not yet implemented")


def refund_credits(org_id: str, amount: int) -> None:
    """
    Refund `amount` run credits to an org (called on task failure).

    TODO [P1]: Implement with session_scope()
    """
    raise NotImplementedError("refund_credits not yet implemented")
