"""
End-to-end API smoke test against a real uvicorn server.

Run:  PYTHONPATH=. python scripts/api_smoke.py

Companion to scripts/ws_smoke.py. This exists because TestClient is not the
production stack: it was passing the whole Phase 0.3 suite while login and
signup returned 500 to every real HTTP client, because slowapi's header
injection behaves differently once the response actually travels over the wire.
Anything that touches middleware ordering, response headers or the ASGI stack
gets checked here as well as in pytest.

Exits non-zero on the first failing expectation, so it can gate a merge.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

# A throwaway database, and the limiter explicitly on — the suite disables it.
_fd, _db = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.unlink(_db)
os.environ.setdefault("ORION_ENV", "dev")
os.environ["ORION_DATABASE_URL"] = "sqlite:///" + _db.replace("\\", "/")
os.environ["ORION_RATE_LIMIT_ENABLED"] = "true"

import uvicorn  # noqa: E402
from arep.api.app import create_app  # noqa: E402

HOST, PORT = "127.0.0.1", 8123
BASE = f"http://{HOST}:{PORT}"

_failures: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(
        ("  PASS  " if ok else "  FAIL  ") + label + ("" if ok else f"   <- {detail}")
    )
    if not ok:
        _failures.append(label)


_cookies: dict[str, str] = {}
# Per-cookie attributes. A response can carry several Set-Cookie headers and the
# flattened header dict keeps only the last, so reading flags from there reports
# the CSRF cookie's attributes for the session cookie.
_cookie_flags: dict[str, str] = {}


def call(
    method: str, path: str, body=None, headers=None, origin=None, use_cookies=False
):
    """Return (status, lowercased headers, body text).

    Header names are lowercased because uvicorn emits them that way on the wire,
    unlike TestClient's case-insensitive mapping — a difference that silently
    broke the first version of this script.
    """
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if origin:
        req.add_header("Origin", origin)
    if use_cookies and _cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in _cookies.items()))
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as response:
            _remember_cookies(response.headers)
            return (
                response.status,
                {k.lower(): v for k, v in response.headers.items()},
                response.read().decode(),
            )
    except urllib.error.HTTPError as exc:
        return (
            exc.code,
            {k.lower(): v for k, v in exc.headers.items()},
            exc.read().decode(),
        )


def _remember_cookies(headers) -> None:
    """Keep Set-Cookie values and attributes, the way a browser would."""
    for raw in headers.get_all("Set-Cookie") or []:
        name, _, rest = raw.partition("=")
        _cookies[name.strip()] = rest.split(";", 1)[0]
        _cookie_flags[name.strip()] = raw


def main() -> int:
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host=HOST,
            port=PORT,
            log_level="error",
        )
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        print("server did not start")
        return 1

    print("\n-- health + security headers (D-03) --")
    status, headers, _ = call("GET", "/health")
    check("GET /health 200", status == 200, status)
    check(
        "nosniff",
        headers.get("x-content-type-options") == "nosniff",
        headers.get("x-content-type-options"),
    )
    check(
        "frame-options DENY",
        headers.get("x-frame-options") == "DENY",
        headers.get("x-frame-options"),
    )
    check(
        "CSP locked down",
        "default-src 'none'" in headers.get("content-security-policy", ""),
        headers.get("content-security-policy"),
    )
    check(
        "no HSTS over plain http",
        "strict-transport-security" not in headers,
        headers.get("strict-transport-security"),
    )

    print("\n-- CORS whitelist (D-03) --")
    _, headers, _ = call("GET", "/health", origin="https://evil.example")
    check(
        "foreign origin gets no grant",
        headers.get("access-control-allow-origin") is None,
        headers.get("access-control-allow-origin"),
    )
    _, headers, _ = call("GET", "/health", origin="http://localhost:5173")
    check(
        "whitelisted origin granted",
        headers.get("access-control-allow-origin") == "http://localhost:5173",
        headers.get("access-control-allow-origin"),
    )

    print("\n-- route auth (D-07) --")
    for path in ("/models/", "/scenarios/", "/jobs/", "/results/model/x", "/api/runs/"):
        status, _, _ = call("GET", path)
        check(f"unauthenticated {path} -> 401", status == 401, status)

    print("\n-- signup / login / authenticated reads --")
    status, _, body = call(
        "POST",
        "/api/auth/signup",
        {
            "email": "smoke@example.com",
            "username": "smoke",
            "password": "smoke-password-123",
            "org_name": "Smoke Org",
        },
    )
    check("signup 201", status == 201, f"{status} {body[:160]}")

    # Signup leaves the address unverified (D-04), which blocks key creation
    # below. Flipping the column is the local stand-in for clicking the link;
    # the real flow has its own tests.
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email="smoke@example.com").first()
        if user is not None:
            user.email_verified = True

    status, headers, body = call(
        "POST",
        "/api/auth/login",
        {
            "identifier": "smoke@example.com",
            "password": "smoke-password-123",
        },
    )
    check("login 200", status == 200, f"{status} {body[:160]}")
    token = json.loads(body)["access_token"] if status == 200 else ""
    auth = {"Authorization": f"Bearer {token}"}

    status, _, body = call("GET", "/scenarios/", headers=auth)
    check("authenticated /scenarios/ 200", status == 200, f"{status} {body[:120]}")
    status, _, body = call("GET", "/models/", headers=auth)
    check(
        "authenticated /models/ lists built-ins",
        status == 200 and "EmergencyBrake" in body,
        f"{status} {body[:120]}",
    )

    print("\n-- rate limiting (D-03) --")
    # The successful login above already spent one of the five per-minute
    # attempts, so four real 401s remain before the limiter takes over.
    codes = [
        call(
            "POST",
            "/api/auth/login",
            {"identifier": "smoke@example.com", "password": "wrong"},
        )[0]
        for _ in range(7)
    ]
    check("remaining budget answers with real 401s", codes[:4] == [401] * 4, codes)
    check("limit then holds", set(codes[5:]) == {429}, codes)

    status, headers, _ = call(
        "POST",
        "/api/auth/login",
        {"identifier": "smoke@example.com", "password": "wrong"},
    )
    check("429 body is the platform error shape", status == 429)
    check(
        "rate-limit headers reach the client",
        "x-ratelimit-limit" in headers,
        sorted(k for k in headers if "ratelimit" in k),
    )

    print("\n-- health stays exempt --")
    check("health still 200 after the limit bit", call("GET", "/health")[0] == 200)

    print("\n-- cookie session + CSRF (D-04) --")
    # No second login here: the per-IP budget is spent by the rate-limit section
    # above, and the cookies from the successful login are still in _cookies —
    # which is the point, a browser keeps them across requests.
    check("session cookie issued", "orion_session" in _cookies, sorted(_cookies))
    check("csrf cookie issued", "orion_csrf" in _cookies, sorted(_cookies))
    check(
        "session cookie is HttpOnly",
        "HttpOnly" in _cookie_flags.get("orion_session", ""),
        _cookie_flags.get("orion_session", "")[:100],
    )
    check(
        "csrf cookie is readable on purpose",
        "HttpOnly" not in _cookie_flags.get("orion_csrf", ""),
        _cookie_flags.get("orion_csrf", "")[:100],
    )

    status, _, _ = call("GET", "/api/auth/me", use_cookies=True)
    check("cookie alone authenticates /me", status == 200, status)

    status, _, body = call("POST", "/api/keys/", {"label": "no-csrf"}, use_cookies=True)
    # Assert *why* it was refused: the verification gate also answers 403, and a
    # test that cannot tell them apart passes for the wrong reason.
    check(
        "cookie write without CSRF is refused",
        status == 403 and "CSRF" in body,
        f"{status} {body[:120]}",
    )

    status, _, body = call(
        "POST",
        "/api/keys/",
        {"label": "with-csrf"},
        headers={"X-CSRF-Token": _cookies.get("orion_csrf", "")},
        use_cookies=True,
    )
    check("cookie write with CSRF is allowed", status == 201, f"{status} {body[:100]}")

    print("\n-- webhook (0.3) --")
    status, _, body = call(
        "POST", "/api/billing/webhook", {"id": "evt_smoke", "type": "invoice.paid"}
    )
    check(
        "unsigned beta webhook is a 200 no-op",
        status == 200 and "beta_noop" in body,
        f"{status} {body[:80]}",
    )

    server.should_exit = True
    print(
        "\n"
        + (
            "ALL SMOKE CHECKS PASSED"
            if not _failures
            else f"FAILURES ({len(_failures)}): {_failures}"
        )
    )
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
