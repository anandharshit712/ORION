"""
Webhook registration and dispatch (Phase 3.1).

Lets a customer say "call me when it's done" instead of polling. That is what
makes ORION part of a pipeline rather than a site you visit, and it is what
`regression.detected` needs in order to fail a build automatically.

The security-sensitive half lives in `webhook_safety` (which URLs may be
contacted) and `webhook_delivery` (how). This module is registration, storage
and fan-out.
"""

from __future__ import annotations

import datetime
import secrets
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal, require_verified_email
from arep.api.webhook_safety import UnsafeWebhookURL, validate_webhook_url
from arep.database.connection import session_scope
from arep.database.models import WebhookDeliveryRecord, WebhookRecord
from arep.utils.logging_config import get_logger

logger = get_logger("api.webhooks")

webhooks_router = APIRouter(
    prefix="/api/webhooks",
    tags=["Webhooks"],
    dependencies=[Depends(get_request_principal)],
)

# Events a customer may subscribe to. An explicit set, so a typo is rejected at
# registration rather than producing a webhook that silently never fires.
VALID_EVENTS = {
    "run.completed",
    "batch.completed",
    "regression.detected",
    "search.completed",
    "comparison.completed",
}

# One endpoint that has failed this many times in a row is disabled. Retrying an
# address nobody is listening at forever costs worker time and achieves nothing.
MAX_CONSECUTIVE_FAILURES = 20

# Per org. Enough for separate dev/staging/prod receivers, few enough that a
# compromised account cannot turn ORION into a fan-out amplifier.
MAX_WEBHOOKS_PER_ORG = 10


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., description="HTTPS endpoint to POST to")
    events: List[str] = Field(
        ..., min_length=1, description=f"Any of {sorted(VALID_EVENTS)}"
    )
    secret: Optional[str] = Field(
        None,
        min_length=16,
        max_length=128,
        description="Shared secret for the HMAC signature. Generated if omitted.",
    )


class WebhookResponse(BaseModel):
    id: int
    url: str
    events: List[str]
    active: bool
    created_at: datetime.datetime
    last_delivery_at: Optional[datetime.datetime] = None
    consecutive_failures: int = 0
    # Returned only when the webhook is created, and never again — the same
    # contract every API key follows, for the same reason.
    secret: Optional[str] = None


class WebhookDeliveryResponse(BaseModel):
    id: int
    event: str
    delivered: bool
    status_code: Optional[int] = None
    duration_ms: int
    error: Optional[str] = None
    attempt: int
    created_at: datetime.datetime


@webhooks_router.post(
    "/",
    response_model=WebhookResponse,
    status_code=201,
    dependencies=[Depends(require_verified_email)],
)
def create_webhook(req: WebhookCreateRequest, request: Request):
    """Register an endpoint. The secret is shown once and never again."""
    org_id, _, _ = get_request_principal(request)

    unknown = sorted(set(req.events) - VALID_EVENTS)
    if unknown:
        # Rejected rather than ignored: a typo that silently never fires is
        # worse than an error, because the customer waits for a call that will
        # not come.
        raise HTTPException(
            400, f"Unknown event(s) {unknown}; valid events are {sorted(VALID_EVENTS)}"
        )

    try:
        validate_webhook_url(req.url)
    except UnsafeWebhookURL as exc:
        raise HTTPException(400, f"Webhook URL rejected: {exc}")

    secret = req.secret or secrets.token_urlsafe(32)

    with session_scope() as db:
        existing = (
            db.query(WebhookRecord).filter(WebhookRecord.org_id == org_id).count()
        )
        if existing >= MAX_WEBHOOKS_PER_ORG:
            raise HTTPException(
                400,
                f"This organisation already has {existing} webhooks "
                f"(limit {MAX_WEBHOOKS_PER_ORG}). Delete one first.",
            )

        hook = WebhookRecord(
            org_id=org_id,
            url=req.url.strip(),
            events="\n".join(sorted(set(req.events))),
            secret=secret,
        )
        db.add(hook)
        db.flush()

        return WebhookResponse(
            id=hook.id,
            url=hook.url,
            events=hook.events.splitlines(),
            active=hook.active,
            created_at=hook.created_at,
            secret=secret,
        )


@webhooks_router.get("/", response_model=List[WebhookResponse])
def list_webhooks(request: Request):
    """This org's webhooks. Secrets are never included."""
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        hooks = (
            db.query(WebhookRecord)
            .filter(WebhookRecord.org_id == org_id)
            .order_by(WebhookRecord.id)
            .all()
        )
        return [
            WebhookResponse(
                id=h.id,
                url=h.url,
                events=h.events.splitlines(),
                active=h.active,
                created_at=h.created_at,
                last_delivery_at=h.last_delivery_at,
                consecutive_failures=h.consecutive_failures,
            )
            for h in hooks
        ]


@webhooks_router.get(
    "/{webhook_id}/deliveries", response_model=List[WebhookDeliveryResponse]
)
def list_deliveries(webhook_id: int, request: Request, limit: int = 50):
    """Recent delivery attempts, so a customer can debug their own endpoint.

    Outcomes only. No response body is stored, so none can be shown — echoing
    it would turn a webhook into a way to read whatever the URL pointed at.
    """
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        hook = db.get(WebhookRecord, webhook_id)
        if hook is None or hook.org_id != org_id:
            raise HTTPException(404, "Webhook not found")

        rows = (
            db.query(WebhookDeliveryRecord)
            .filter(WebhookDeliveryRecord.webhook_id == webhook_id)
            .order_by(WebhookDeliveryRecord.id.desc())
            .limit(limit)
            .all()
        )
        return [
            WebhookDeliveryResponse(
                id=r.id,
                event=r.event,
                delivered=r.delivered,
                status_code=r.status_code,
                duration_ms=r.duration_ms,
                error=r.error,
                attempt=r.attempt,
                created_at=r.created_at,
            )
            for r in rows
        ]


@webhooks_router.delete("/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, request: Request):
    org_id, _, _ = get_request_principal(request)

    with session_scope() as db:
        hook = db.get(WebhookRecord, webhook_id)
        if hook is None or hook.org_id != org_id:
            raise HTTPException(404, "Webhook not found")
        db.delete(hook)

    return None


# ── Dispatch ─────────────────────────────────────────────────────────────


def dispatch(event: str, org_id: Optional[str], payload: Dict[str, Any]) -> int:
    """Notify every active webhook in `org_id` subscribed to `event`.

    Returns how many were attempted. Never raises: the caller is a worker
    finishing a batch, and a customer's broken endpoint must not fail the run
    they paid for.
    """
    if org_id is None:
        return 0

    try:
        return _dispatch(event, org_id, payload)
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception("Webhook dispatch failed for %s / org %s", event, org_id)
        return 0


def _dispatch(event: str, org_id: str, payload: Dict[str, Any]) -> int:
    from arep.api.webhook_delivery import deliver

    with session_scope() as db:
        hooks = (
            db.query(WebhookRecord)
            .filter(
                WebhookRecord.org_id == org_id,
                WebhookRecord.active.is_(True),
            )
            .all()
        )
        targets = [
            (h.id, h.url, h.secret) for h in hooks if event in h.events.splitlines()
        ]

    if not targets:
        return 0

    body = {
        "event": event,
        "sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "data": payload,
    }

    for webhook_id, url, secret in targets:
        outcome = deliver(url=url, secret=secret, event=event, payload=body)

        with session_scope() as db:
            db.add(
                WebhookDeliveryRecord(
                    webhook_id=webhook_id,
                    event=event,
                    delivered=outcome.delivered,
                    status_code=outcome.status_code,
                    duration_ms=outcome.duration_ms,
                    error=outcome.error,
                    attempt=1,
                )
            )

            hook = db.get(WebhookRecord, webhook_id)
            if hook is not None:
                hook.last_delivery_at = datetime.datetime.utcnow()
                if outcome.delivered:
                    hook.consecutive_failures = 0
                else:
                    hook.consecutive_failures += 1
                    if hook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        # Disabled, not deleted: the customer can see why it
                        # stopped and re-enable it once their endpoint is back.
                        hook.active = False
                        logger.warning(
                            "Disabled webhook %s after %d consecutive failures",
                            webhook_id,
                            hook.consecutive_failures,
                        )

    return len(targets)
