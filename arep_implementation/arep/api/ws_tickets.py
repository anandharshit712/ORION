"""
Short-lived, single-use tickets for WebSocket authentication (Phase 0.4, D-04).

A browser cannot set an Authorization header on a WebSocket handshake, so the
credential has to travel in the URL. Sending the session JWT there put a
long-lived credential into every access log, proxy log, referrer header and
browser history entry along the path — one log export and the token is usable
until it expires.

A ticket is a random opaque string that buys exactly one WebSocket connection to
exactly one run, within sixty seconds. Leaking it after the fact is worthless.

ponytail: in-memory store, single process. That matches sim_registry, which
holds the live runs in this process too — a ticket is only ever redeemed by the
worker that issued it, because only that worker has the run. If live runs ever
move behind a load balancer, both this and sim_registry need Redis, and they
need it together.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

from arep.utils.logging_config import get_logger

logger = get_logger("api.ws_tickets")

# Sixty seconds is the roadmap figure: long enough for a page to receive the
# response and open the socket, short enough that a captured URL is useless by
# the time anyone reads the log it landed in.
TICKET_TTL_SECONDS = 60.0


@dataclass
class _Ticket:
    run_id: str
    user_id: int
    org_id: Optional[str]
    expires_at: float


_tickets: Dict[str, _Ticket] = {}


def _prune(now: float) -> None:
    """Drop expired tickets.

    Called on issue rather than from a timer: tickets live for a minute, the
    dictionary only grows when runs are being started, and a background task
    would be a moving part to own for no gain.
    """
    for key in [k for k, t in _tickets.items() if t.expires_at <= now]:
        _tickets.pop(key, None)


def issue_ticket(run_id: str, user_id: int, org_id: Optional[str]) -> tuple[str, int]:
    """Mint a ticket for one run. Returns (ticket, ttl_seconds)."""
    now = time.monotonic()
    _prune(now)

    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = _Ticket(
        run_id=run_id,
        user_id=user_id,
        org_id=org_id,
        expires_at=now + TICKET_TTL_SECONDS,
    )
    logger.info("WS ticket issued for run_id=%s user_id=%s", run_id, user_id)
    return ticket, int(TICKET_TTL_SECONDS)


def redeem_ticket(ticket: str, run_id: str) -> Optional[tuple[int, Optional[str]]]:
    """Consume a ticket. Returns (user_id, org_id), or None if it is not good.

    Removed on the first read whatever the outcome, so a replay of the same
    string fails even if it has not expired. Bound to the run it was issued for:
    a ticket for one run must not open a socket onto another.
    """
    entry = _tickets.pop(ticket, None)
    if entry is None:
        return None
    if entry.expires_at <= time.monotonic():
        return None
    if entry.run_id != run_id:
        # Already consumed above, which is the right call — a ticket presented
        # against the wrong run is either a bug or probing, and neither deserves
        # a second attempt.
        logger.warning(
            "WS ticket presented for the wrong run (wanted %s)", entry.run_id
        )
        return None
    return entry.user_id, entry.org_id


def clear_tickets() -> None:
    """Drop every outstanding ticket. For tests."""
    _tickets.clear()
