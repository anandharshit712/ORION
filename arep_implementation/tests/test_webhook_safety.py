"""
Outbound-request safety for webhook URLs (Phase 3.1).

These are the tests that matter most in the webhook feature. A webhook makes
ORION's server fetch an address the customer chose, from inside the network the
customer cannot reach — so a gap here is not a bug in a feature, it is a way to
read the instance's cloud credentials.

Each test names the attack it blocks. A test that only checks "returns True for
https://example.com" would pass against a function that blocks nothing.
"""

from __future__ import annotations

import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.api.webhook_safety import (  # noqa: E402
    ALLOWED_PORTS,
    UnsafeWebhookURL,
    validate_webhook_url,
)


def _resolve_to(monkeypatch, *addresses):
    """Pin DNS so these tests never depend on the network."""

    def fake(hostname, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


# -- The addresses that matter --------------------------------------------


def test_the_cloud_metadata_endpoint_is_refused(monkeypatch):
    """169.254.169.254 hands out the instance's cloud credentials. It is
    unreachable from the internet and freely readable from inside, which is
    exactly what makes a webhook a way to reach it."""
    _resolve_to(monkeypatch, "169.254.169.254")

    with pytest.raises(UnsafeWebhookURL, match="link-local"):
        validate_webhook_url("http://metadata.example.com/latest/meta-data/")


def test_loopback_is_refused(monkeypatch):
    """127.0.0.1 is Redis, the API itself, anything bound locally."""
    _resolve_to(monkeypatch, "127.0.0.1")

    with pytest.raises(UnsafeWebhookURL, match="loopback"):
        validate_webhook_url("http://localhost/hook")


def test_private_ranges_are_refused(monkeypatch):
    """10/8, 172.16/12 and 192.168/16 are where the database lives."""
    for address in ("10.0.0.5", "172.16.4.4", "192.168.1.10"):
        _resolve_to(monkeypatch, address)
        with pytest.raises(UnsafeWebhookURL, match="private"):
            validate_webhook_url("https://internal.example.com/hook")


def test_an_ipv4_mapped_ipv6_address_does_not_sneak_through(monkeypatch):
    """::ffff:169.254.169.254 is the metadata endpoint wearing an IPv6 hat, and
    a CIDR list written for IPv4 misses it completely."""
    _resolve_to(monkeypatch, "::ffff:169.254.169.254")

    with pytest.raises(UnsafeWebhookURL, match="link-local"):
        validate_webhook_url("http://sneaky.example.com/hook")


def test_ipv6_loopback_is_refused(monkeypatch):
    _resolve_to(monkeypatch, "::1")
    with pytest.raises(UnsafeWebhookURL, match="loopback"):
        validate_webhook_url("http://v6.example.com/hook")


def test_a_bare_ip_literal_is_checked_too(monkeypatch):
    """Skipping the check for literals because "there is no DNS to rebind"
    would be the easiest possible bypass."""
    _resolve_to(monkeypatch, "169.254.169.254")
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("http://169.254.169.254/latest/meta-data/")


def test_every_resolved_address_must_pass_not_just_the_first(monkeypatch):
    """A name resolving to one public and one private address is a rebinding
    attempt waiting to happen, and round-robin DNS makes it intermittent —
    which is worse than failing outright."""
    _resolve_to(monkeypatch, "93.184.216.34", "10.0.0.5")

    with pytest.raises(UnsafeWebhookURL, match="private"):
        validate_webhook_url("https://mixed.example.com/hook")


# -- Schemes, ports and shape ---------------------------------------------


def test_non_http_schemes_are_refused():
    """file:// and gopher:// turn a URL fetch into something else entirely."""
    for url in ("file:///etc/passwd", "gopher://x/1", "ftp://x/y"):
        with pytest.raises(UnsafeWebhookURL, match="scheme"):
            validate_webhook_url(url)


def test_internal_service_ports_are_refused(monkeypatch):
    """Restricting ports removes a large class of internal probing — Redis
    6379, Postgres 5432 — and costs nothing: real receivers are on 80 or 443."""
    _resolve_to(monkeypatch, "93.184.216.34")

    for port in (22, 5432, 6379, 11211, 9200):
        with pytest.raises(UnsafeWebhookURL, match="port"):
            validate_webhook_url(f"https://example.com:{port}/hook")


def test_the_usual_ports_are_allowed(monkeypatch):
    _resolve_to(monkeypatch, "93.184.216.34")
    for port in sorted(ALLOWED_PORTS):
        target = validate_webhook_url(f"https://example.com:{port}/hook")
        assert target.port == port


def test_credentials_in_the_url_are_refused(monkeypatch):
    """A redirect-laundering trick, and pointless here: the shared secret is
    what proves the request came from us."""
    _resolve_to(monkeypatch, "93.184.216.34")

    with pytest.raises(UnsafeWebhookURL, match="credentials"):
        validate_webhook_url("https://user:pass@example.com/hook")


def test_a_hostname_that_does_not_resolve_is_refused(monkeypatch):
    _resolve_to(monkeypatch)  # resolves to nothing
    with pytest.raises(UnsafeWebhookURL, match="does not resolve"):
        validate_webhook_url("https://nowhere.example.com/hook")


def test_an_absurdly_long_url_is_refused():
    with pytest.raises(UnsafeWebhookURL):
        validate_webhook_url("https://example.com/" + "a" * 4000)


def test_empty_and_hostless_urls_are_refused():
    for url in ("", "https://", "not-a-url"):
        with pytest.raises(UnsafeWebhookURL):
            validate_webhook_url(url)


# -- The happy path --------------------------------------------------------


def test_an_ordinary_public_url_passes_and_pins_its_address(monkeypatch):
    """The resolved address comes back so the request can be sent to *it*
    rather than re-resolving — that is what closes the rebinding window."""
    _resolve_to(monkeypatch, "93.184.216.34")

    target = validate_webhook_url("https://hooks.example.com/orion")

    assert target.hostname == "hooks.example.com"
    assert target.ip == "93.184.216.34"
    assert target.port == 443
    assert target.scheme == "https"


def test_the_refusal_reason_does_not_confirm_what_is_listening(monkeypatch):
    """The message must help fix a typo without reporting whether something is
    actually running at that address — that difference is how a network gets
    mapped."""
    _resolve_to(monkeypatch, "10.0.0.5")

    with pytest.raises(UnsafeWebhookURL) as excinfo:
        validate_webhook_url("https://internal.example.com/hook")

    message = str(excinfo.value)
    assert "private" in message
    for leak in ("refused", "timeout", "open", "closed", "listening"):
        assert leak not in message.lower()


# ── Delivery ─────────────────────────────────────────────────────────────


def test_the_signature_matches_the_bytes_that_were_sent():
    """Signing a re-serialised copy would have the customer verifying a
    different payload than the one they received."""
    import hashlib
    import hmac

    from arep.api.webhook_delivery import sign

    secret, timestamp, body = "shh", "1700000000", b'{"a":1}'
    expected = hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()

    assert sign(secret, timestamp, body) == expected


def test_the_timestamp_is_inside_the_signed_material():
    """Otherwise a captured delivery can be replayed later unchanged."""
    from arep.api.webhook_delivery import sign

    body = b'{"a":1}'
    assert sign("shh", "1700000000", body) != sign("shh", "1700000001", body)


def test_a_different_secret_gives_a_different_signature():
    from arep.api.webhook_delivery import sign

    assert sign("a", "1", b"{}") != sign("b", "1", b"{}")


def test_delivery_revalidates_the_url_at_send_time(monkeypatch):
    """The whole rebinding attack is DNS changing between registration and
    send, so a URL checked only when registered is not checked at all."""
    from arep.api import webhook_delivery

    _resolve_to(monkeypatch, "169.254.169.254")

    outcome = webhook_delivery.deliver(
        url="https://was-fine-yesterday.example.com/hook",
        secret="shh",
        event="batch.completed",
        payload={"batch_id": 1},
    )

    assert outcome.delivered is False
    assert outcome.error == "url_rejected"


def test_an_unreachable_endpoint_is_reported_as_one_category(monkeypatch):
    """ "Refused in 1 ms" and "timed out after 5 s" map the internal network
    even when the body is discarded, so both collapse to the same word."""
    import urllib.request

    from arep.api import webhook_delivery

    _resolve_to(monkeypatch, "93.184.216.34")

    def boom(*args, **kwargs):
        raise ConnectionRefusedError("connection refused to 10.0.0.5:6379")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", boom)

    outcome = webhook_delivery.deliver(
        url="https://example.com/hook", secret="s", event="e", payload={}
    )

    assert outcome.delivered is False
    assert outcome.error == "unreachable"
    # The transport's own message must not survive into the record.
    assert "10.0.0.5" not in str(outcome.error)
    assert "refused" not in str(outcome.error)


def test_delivery_never_raises(monkeypatch):
    """The caller is a worker finishing a batch. A customer's broken endpoint
    must not fail the run they paid for."""
    import urllib.request

    from arep.api import webhook_delivery

    _resolve_to(monkeypatch, "93.184.216.34")

    def explode(*args, **kwargs):
        raise RuntimeError("something entirely unexpected")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", explode)

    outcome = webhook_delivery.deliver(
        url="https://example.com/hook", secret="s", event="e", payload={}
    )
    assert outcome.delivered is False


def test_redirects_are_refused_by_the_opener():
    """A validated URL answering "302, try 169.254.169.254" would otherwise
    walk straight past every check above."""
    import inspect

    from arep.api import webhook_delivery

    source = inspect.getsource(webhook_delivery.deliver)
    assert "_NoRedirect" in source
    assert "redirect_request" in source
    assert "return None" in source
