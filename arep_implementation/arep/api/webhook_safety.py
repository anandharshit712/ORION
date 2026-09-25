"""
Outbound-request safety for customer-supplied webhook URLs (Phase 3.1).

A webhook is "the customer gives us an address and our server makes a request to
it". Our server sits inside the network; the customer does not. Without the
checks here, a webhook URL is a way to make ORION fetch things on the customer's
behalf that they could never reach themselves — the cloud metadata endpoint that
hands out instance credentials, the database, Redis, anything bound to loopback.

Three things make a naive blocklist insufficient, and each is handled here:

1. **DNS rebinding.** Validating the hostname is not validating what you connect
   to. A name can resolve to a public address when checked and to 127.0.0.1 a
   moment later. So resolution happens once, every returned address is checked,
   and the request is sent to a *pinned* address rather than re-resolving.

2. **Redirects.** A harmless URL can answer "302, try 169.254.169.254". Any
   HTTP client that follows redirects bypasses the check entirely. Redirects are
   never followed.

3. **Timing as a side channel.** Even with the response discarded, "refused in
   1 ms" versus "timed out after 5 s" maps the internal network. A single short
   timeout is used for every outcome, and delivery records store whether it
   worked, never the response body or a distinguishable error.

None of this is exotic. It is a list where missing one item gives away the whole
thing.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urlparse

from arep.utils.logging_config import get_logger

logger = get_logger("api.webhook_safety")

# Only these schemes. No file://, no gopher://, no ftp:// — all of which have
# been used to turn a URL fetch into something else entirely.
ALLOWED_SCHEMES = {"http", "https"}

# Ports a webhook may target. Restricting these removes a large class of
# internal-service probing (Redis 6379, Postgres 5432, memcached 11211) without
# inconveniencing anyone: a real webhook receiver is on 80 or 443.
ALLOWED_PORTS = {80, 443, 8080, 8443}

MAX_URL_LENGTH = 2048


class UnsafeWebhookURL(ValueError):
    """The URL is not one we are willing to send a request to."""


@dataclass(frozen=True)
class ResolvedTarget:
    """A URL that passed validation, with the address it resolved to.

    The address is carried so the request can be sent to *this* IP rather than
    re-resolving the hostname — which is what closes the rebinding window.
    """

    url: str
    hostname: str
    ip: str
    port: int
    scheme: str


def _is_forbidden_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> Tuple[bool, str]:
    """Whether this address is one we refuse to connect to, and why.

    Checked with `ipaddress` rather than a hand-written CIDR list: the standard
    library already knows about every range that matters, including the ones
    people forget — IPv4-mapped IPv6 (::ffff:169.254.169.254), 6to4, and
    0.0.0.0/8.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # ::ffff:127.0.0.1 is loopback wearing an IPv6 hat.
        return _is_forbidden_ip(ip.ipv4_mapped)

    if ip.is_loopback:
        return True, "loopback"
    if ip.is_link_local:
        # 169.254.0.0/16 — the cloud metadata endpoint lives here.
        return True, "link-local (cloud metadata lives here)"
    if ip.is_private:
        return True, "private network"
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True, "reserved, multicast or unspecified"

    return False, ""


def validate_webhook_url(url: str) -> ResolvedTarget:
    """Check a customer-supplied URL, resolve it, and pin the address.

    Raises `UnsafeWebhookURL` with a reason the customer can act on. The reason
    deliberately says *what kind* of address was refused without confirming
    whether something is listening there — enough to fix a typo, not enough to
    map the network.
    """
    if not url or len(url) > MAX_URL_LENGTH:
        raise UnsafeWebhookURL(f"URL must be 1-{MAX_URL_LENGTH} characters")

    parsed = urlparse(url.strip())

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeWebhookURL(
            f"scheme {parsed.scheme!r} is not allowed; use http or https"
        )

    if not parsed.hostname:
        raise UnsafeWebhookURL("URL has no host")

    # Credentials in the URL are a redirect-laundering trick and have no place
    # in a webhook target; the secret is what authenticates us.
    if parsed.username or parsed.password:
        raise UnsafeWebhookURL("credentials in the URL are not supported")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeWebhookURL(
            f"port {port} is not allowed; use one of {sorted(ALLOWED_PORTS)}"
        )

    addresses = _resolve(parsed.hostname)
    if not addresses:
        raise UnsafeWebhookURL(f"{parsed.hostname!r} does not resolve")

    # *Every* address must be acceptable, not just the first. A name that
    # resolves to one public and one private address is a rebinding attempt
    # waiting to happen, and round-robin DNS would make it intermittent.
    for address in addresses:
        forbidden, reason = _is_forbidden_ip(ipaddress.ip_address(address))
        if forbidden:
            raise UnsafeWebhookURL(
                f"{parsed.hostname!r} resolves to a {reason} address, which "
                f"ORION will not send requests to"
            )

    return ResolvedTarget(
        url=url.strip(),
        hostname=parsed.hostname,
        ip=addresses[0],
        port=port,
        scheme=parsed.scheme,
    )


def _resolve(hostname: str) -> List[str]:
    """Every address a hostname resolves to, IPv4 and IPv6.

    A bare IP literal resolves to itself, which is what we want: it still goes
    through the forbidden-range check below.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []

    seen: List[str] = []
    for info in infos:
        # sockaddr is (host, port) for IPv4 and (host, port, flow, scope) for
        # IPv6; the host is first in both, and is always a string here because
        # getaddrinfo was asked for numeric results.
        address = str(info[4][0])
        if address not in seen:
            seen.append(address)
    return seen
