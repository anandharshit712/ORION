"""
API surface hardening tests (Phase 0.3, defect D-03).

Covers the roadmap acceptance criteria:
  - a request from a non-whitelisted origin gets no CORS grant
  - the 6th login attempt in a minute from one IP gets a 429
  - security headers are present on API responses
  - a wildcard / empty CORS whitelist is refused outside dev

D-07 (auth on /models/, /scenarios/, /jobs/, /results/*) is covered in
tests/test_route_auth.py.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WHITELISTED_ORIGIN = "http://localhost:5173"   # the Vite dev server; see APIConfig
FOREIGN_ORIGIN = "https://evil.example"
API_CSP = "default-src 'none'; frame-ancestors 'none'"


@pytest.fixture(scope="module")
def client():
    """TestClient on a throwaway SQLite file, mirroring test_multitenancy."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    from arep.database import connection as conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

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


@pytest.fixture
def live_limiter():
    """Turn the limiter on for one test and leave it off afterwards.

    conftest.py disables it for the rest of the suite. Storage is reset on both
    sides so counters never leak between tests - slowapi's memory storage is
    process-global.
    """
    from arep.api.ratelimit import limiter

    previous = limiter.enabled
    limiter.reset()
    limiter.enabled = True
    yield limiter
    limiter.reset()
    limiter.enabled = previous


# -- CORS (D-03) ----------------------------------------------------------

def test_whitelisted_origin_gets_cors_grant(client):
    r = client.options(
        "/health",
        headers={
            "Origin": WHITELISTED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == WHITELISTED_ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


def test_foreign_origin_gets_no_cors_grant(client):
    """The D-03 acceptance criterion."""
    r = client.options(
        "/health",
        headers={
            "Origin": FOREIGN_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in r.headers

    # A simple (non-preflight) request still executes - CORS is enforced by the
    # browser, not the server - but must not carry the grant header that would
    # let a page read the response.
    r2 = client.get("/health", headers={"Origin": FOREIGN_ORIGIN})
    assert r2.headers.get("access-control-allow-origin") is None


def test_wildcard_origin_is_never_echoed(client):
    """Regression guard for the original defect: allow_origins=["*"]."""
    r = client.get("/health", headers={"Origin": FOREIGN_ORIGIN})
    assert r.headers.get("access-control-allow-origin") != "*"


# -- Security headers (D-03) ----------------------------------------------

def test_security_headers_present_on_api_response(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Content-Security-Policy"] == API_CSP


def test_security_headers_present_on_error_response(client):
    """A 401 body is still a body a browser could be tricked into rendering."""
    r = client.get("/jobs/")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_docs_get_a_relaxed_csp(client):
    """A default-src 'none' policy would render Swagger UI blank."""
    r = client.get("/docs")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp
    assert csp != API_CSP


def test_hsts_absent_over_plain_http(client):
    """Browsers ignore HSTS over http://; asserting it there is noise."""
    r = client.get("/health")
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_present_when_proxy_reports_https(client):
    r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age=31536000" in r.headers["Strict-Transport-Security"]


# -- Rate limiting (D-03) -------------------------------------------------

def test_sixth_login_in_a_minute_is_rejected(client, live_limiter):
    """The D-03 acceptance criterion: login is 5/minute per IP.

    Credentials are deliberately wrong - the limit must bite regardless of
    whether the account exists, or it is not a credential-stuffing control.
    The body must still be *well-formed*: FastAPI validates it before calling
    the endpoint, so a malformed body 422s without ever reaching the route
    decorator. Those requests still count against the global 120/minute
    default enforced by SlowAPIMiddleware, which runs earlier in the stack.
    """
    payload = {"identifier": "nobody@example.com", "password": "wrong-password"}

    for attempt in range(5):
        r = client.post("/api/auth/login", json=payload)
        assert r.status_code != 429, f"limited too early on attempt {attempt + 1}"

    r = client.post("/api/auth/login", json=payload)
    assert r.status_code == 429


def test_rate_limit_error_uses_the_platform_error_shape(client, live_limiter):
    """Every other API error is {"detail": ...}; slowapi's default is {"error": ...}."""
    payload = {"identifier": "nobody@example.com", "password": "wrong-password"}
    for _ in range(6):
        r = client.post("/api/auth/login", json=payload)

    assert r.status_code == 429
    body = r.json()
    assert "detail" in body and "error" not in body
    assert "Rate limit exceeded" in body["detail"]


def test_rate_limited_response_tells_the_client_when_to_retry(client, live_limiter):
    payload = {"identifier": "nobody@example.com", "password": "wrong-password"}
    for _ in range(6):
        r = client.post("/api/auth/login", json=payload)

    assert r.status_code == 429
    assert "Retry-After" in r.headers or "X-RateLimit-Reset" in r.headers


def test_health_is_exempt_from_the_global_limit(client, live_limiter):
    """Liveness probes come from one address every few seconds forever.

    130 > the 120/minute default, so an un-exempted /health would 429 here.
    """
    statuses = {client.get("/health").status_code for _ in range(130)}
    assert statuses == {200}


def test_limiter_disabled_by_config_lets_everything_through(client):
    """conftest sets ORION_RATE_LIMIT_ENABLED=false; the escape hatch must work."""
    from arep.api.ratelimit import limiter

    assert limiter.enabled is False
    payload = {"identifier": "nobody@example.com", "password": "wrong-password"}
    for _ in range(8):
        assert client.post("/api/auth/login", json=payload).status_code != 429


# -- Rate-limit bucketing -------------------------------------------------

def _fake_request(headers: dict, ip: str = "10.0.0.1", **state):
    """Minimal stand-in for a Starlette Request, enough for the key functions."""
    from types import SimpleNamespace

    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=ip),
        state=SimpleNamespace(**state),
    )


def test_authenticated_callers_are_bucketed_per_org_not_per_ip():
    """Two tenants behind one NAT must not share a budget."""
    from arep.api.ratelimit import principal_key

    a = principal_key(_fake_request({}, org_id="org-a", user_id=1))
    b = principal_key(_fake_request({}, org_id="org-b", user_id=2))
    assert a != b
    assert "org-a" in a


def test_unauthenticated_callers_fall_back_to_ip():
    from arep.api.ratelimit import principal_key

    key = principal_key(_fake_request({}, ip="203.0.113.9", org_id=None))
    assert key == "ip:203.0.113.9"


def test_invalid_tokens_are_bucketed_by_credential_hash():
    """OrgAuthMiddleware rejects a bad token before request.state is set.

    Without this tier, a flood of garbage-token requests would share one IP
    bucket at best, and the raw token would land in limiter storage at worst.
    """
    from arep.api.ratelimit import principal_key

    secret = "sk-orion-not-a-real-key"
    key = principal_key(_fake_request({"Authorization": f"Bearer {secret}"}, org_id=None))
    assert key.startswith("cred:")
    assert secret not in key


def test_forwarded_for_is_ignored_unless_the_proxy_is_trusted():
    """Otherwise any client mints itself a fresh bucket per request."""
    from arep.config import get_config, reload_config
    from arep.api.ratelimit import client_ip

    req = _fake_request({"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}, ip="10.0.0.1")

    assert get_config().api.trust_proxy_headers is False
    assert client_ip(req) == "10.0.0.1"

    os.environ["ORION_TRUST_PROXY_HEADERS"] = "true"
    try:
        reload_config()
        assert client_ip(req) == "1.2.3.4"   # leftmost entry = the original client
    finally:
        del os.environ["ORION_TRUST_PROXY_HEADERS"]
        reload_config()


# -- CORS configuration validation (D-03) ---------------------------------

@pytest.fixture
def clean_config():
    """Restore ORION_ENV / ORION_ALLOWED_ORIGINS and the config singleton."""
    from arep.config import reload_config

    saved = {k: os.environ.get(k) for k in ("ORION_ENV", "ORION_ALLOWED_ORIGINS")}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    reload_config()


def test_wildcard_cors_refused_outside_dev(clean_config):
    from arep.config import reload_config
    from arep.config.validate import resolve_cors_origins
    from arep.utils.exceptions import ConfigurationError

    os.environ["ORION_ENV"] = "production"
    os.environ["ORION_ALLOWED_ORIGINS"] = "*"
    reload_config()

    with pytest.raises(ConfigurationError, match="wildcard"):
        resolve_cors_origins()


def test_empty_cors_whitelist_refused_outside_dev(clean_config):
    from arep.config import reload_config
    from arep.config.validate import resolve_cors_origins
    from arep.utils.exceptions import ConfigurationError

    os.environ["ORION_ENV"] = "production"
    os.environ["ORION_ALLOWED_ORIGINS"] = ""
    reload_config()

    with pytest.raises(ConfigurationError, match="empty"):
        resolve_cors_origins()


def test_explicit_whitelist_accepted_outside_dev(clean_config):
    from arep.config import reload_config
    from arep.config.validate import resolve_cors_origins

    os.environ["ORION_ENV"] = "production"
    os.environ["ORION_ALLOWED_ORIGINS"] = "https://app.example.com, https://admin.example.com"
    reload_config()

    assert resolve_cors_origins() == ["https://app.example.com", "https://admin.example.com"]


def test_wildcard_tolerated_in_dev(clean_config):
    """Dev keeps working; the logged warning is the deterrent, not a hard failure."""
    from arep.config import reload_config
    from arep.config.validate import resolve_cors_origins

    os.environ["ORION_ENV"] = "dev"
    os.environ["ORION_ALLOWED_ORIGINS"] = "*"
    reload_config()

    assert resolve_cors_origins() == ["*"]
