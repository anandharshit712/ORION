"""
Sending webhooks (Phase 3.1).

Split from `webhook_safety` on purpose: that module decides *whether* a URL may
be contacted, this one contacts it. Keeping them apart means the validation can
be tested without a network and reviewed on its own, which for the part that
stops SSRF is worth the extra file.

Delivery rules, and why each exists:

- **Redirects are never followed.** A validated URL that answers "302, try
  169.254.169.254" would otherwise walk straight past the check.
- **The response body is read but never stored or returned.** A delivery record
  that echoed the body would turn a webhook into a way to read internal pages.
- **One short timeout for every outcome.** "Refused in 1 ms" versus "hung for
  5 s" maps the internal network even when nothing is echoed.
- **The signature covers the exact bytes sent.** Signing a re-serialised copy
  means the customer verifies a different payload than the one they received.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from arep.api.webhook_safety import UnsafeWebhookURL, validate_webhook_url
from arep.utils.logging_config import get_logger

logger = get_logger("api.webhook_delivery")

# Long enough for a receiver doing something reasonable, short enough that a
# hanging endpoint cannot tie up a worker. The same value is used for connect
# and read so the two are not distinguishable by timing.
DELIVERY_TIMEOUT_S = 5.0

# Read but discarded. Capped so a malicious receiver cannot stream gigabytes
# into a worker that is only checking a status code.
MAX_RESPONSE_BYTES = 8192

SIGNATURE_HEADER = "X-ORION-Signature"
TIMESTAMP_HEADER = "X-ORION-Timestamp"
EVENT_HEADER = "X-ORION-Event"


@dataclass
class DeliveryOutcome:
    """What happened, in terms safe to store.

    No response body and no distinguishable error text: both are side channels.
    `error` carries a category, never the transport's own message.
    """

    delivered: bool
    status_code: Optional[int] = None
    duration_ms: int = 0
    error: Optional[str] = None


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over "<timestamp>.<body>", hex encoded.

    The timestamp is inside the signed material so a captured delivery cannot be
    replayed later against a receiver that checks it — the same construction
    Stripe uses, which means customers already have code that verifies it.
    """
    mac = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    )
    return mac.hexdigest()


def deliver(
    url: str,
    secret: str,
    event: str,
    payload: Dict[str, Any],
    timeout_s: float = DELIVERY_TIMEOUT_S,
) -> DeliveryOutcome:
    """Send one webhook. Never raises.

    A delivery failure is data, not an exception: the caller is a worker
    finishing a batch, and a customer's broken endpoint must not fail the run
    they paid for.
    """
    import urllib.error
    import urllib.request

    started = datetime.datetime.now(datetime.timezone.utc)

    try:
        target = validate_webhook_url(url)
    except UnsafeWebhookURL as exc:
        # Re-validated at send time, not just at registration: DNS can change
        # between the two, which is the entire rebinding attack.
        logger.warning("Refusing webhook delivery to %s: %s", url, exc)
        return DeliveryOutcome(delivered=False, error="url_rejected")

    # Serialise once and sign exactly those bytes. Signing a re-serialised copy
    # would have the customer verifying a different payload than they received.
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    timestamp = str(int(started.timestamp()))

    request = urllib.request.Request(
        target.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ORION-Webhook/1.0",
            EVENT_HEADER: event,
            TIMESTAMP_HEADER: timestamp,
            SIGNATURE_HEADER: sign(secret, timestamp, body),
        },
    )

    # A handler that refuses every redirect. urllib follows them by default, and
    # a 302 to the metadata endpoint would bypass everything above.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(_NoRedirect)

    status: Optional[int] = None
    error: Optional[str] = None
    try:
        with opener.open(request, timeout=timeout_s) as response:
            status = response.status
            response.read(MAX_RESPONSE_BYTES)  # drained, never stored
    except urllib.error.HTTPError as exc:
        # The receiver answered, just not with success. That is a real status
        # worth recording — it tells the customer their endpoint is reachable
        # and returning 500.
        status = exc.code
        exc.read(MAX_RESPONSE_BYTES) if hasattr(exc, "read") else None
    except Exception:  # noqa: BLE001 - see below
        # Everything else collapses to one category on purpose. Distinguishing
        # "connection refused" from "timed out" is how an internal network gets
        # mapped through a webhook endpoint.
        error = "unreachable"

    duration_ms = int(
        (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds() * 1000
    )
    delivered = status is not None and 200 <= status < 300

    return DeliveryOutcome(
        delivered=delivered,
        status_code=status,
        duration_ms=duration_ms,
        error=(
            error if not delivered and error else (None if delivered else "http_error")
        ),
    )
