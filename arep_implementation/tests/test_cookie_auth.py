"""
Cookie session and CSRF tests (Phase 0.4, defect D-04).

Covers the roadmap acceptance criteria "JWT absent from localStorage, present
only as an httpOnly cookie" (the server half — the frontend half is that
AuthContext no longer touches localStorage) and "page refresh keeps the user
logged in (cookie + /me bootstrap)".

Also pins the part that a cookie introduces and a Bearer header does not: the
browser attaches cookies to cross-site requests by itself, so state-changing
calls need a CSRF token.
"""

from __future__ import annotations

import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import verify_email_for  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="module")
def client():
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


@pytest.fixture(scope="module")
def account(client):
    email = "cookie@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "cookieuser",
            "password": PASSWORD,
            "org_name": "Cookie Org",
        },
    )
    assert r.status_code == 201, r.text
    verify_email_for(email)
    return email


@pytest.fixture
def logged_in(client, account):
    """Log in and leave the cookies on the client, as a browser would."""
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    yield r
    client.cookies.clear()


def _csrf(client) -> dict:
    return {"X-CSRF-Token": client.cookies.get("orion_csrf")}


# -- The cookie itself ----------------------------------------------------


def test_login_sets_an_httponly_session_cookie(client, account):
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    assert r.status_code == 200

    set_cookie = r.headers.get("set-cookie", "")
    assert "orion_session=" in set_cookie
    assert "HttpOnly" in set_cookie, "a readable JWT is the defect we are closing"
    assert "SameSite=lax" in set_cookie.replace("samesite", "SameSite")


def test_csrf_cookie_is_readable_on_purpose(client, account):
    """The frontend has to echo it back, so it must not be httpOnly.

    That is safe: a cross-site page can make the browser send the cookie but
    cannot read it, which is exactly what makes double-submit work.
    """
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    csrf_header = [h for h in r.headers.get_list("set-cookie") if "orion_csrf" in h][0]
    assert "HttpOnly" not in csrf_header


def test_login_still_returns_a_bearer_token_for_sdk_clients(client, account):
    """Dropping the body token would break every script and the SDK."""
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    assert r.json()["access_token"]


def test_cookie_alone_authenticates_a_request(client, logged_in):
    """The /me bootstrap the frontend relies on, with no Authorization header."""
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "cookie@example.com"


def test_session_survives_a_simulated_refresh(client, logged_in):
    """The acceptance criterion: a reload keeps the user logged in.

    A refresh throws away all page state; only the cookie persists. Two
    independent /me calls with nothing carried between them stand in for it.
    """
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_logout_clears_the_session(client, logged_in):
    r = client.post("/api/auth/logout", headers=_csrf(client))
    assert r.status_code == 200
    client.cookies.clear()  # the browser would drop the expired cookie
    assert client.get("/api/auth/me").status_code == 401


def test_no_cookie_means_unauthenticated(client):
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_a_garbage_cookie_is_rejected(client):
    client.cookies.clear()
    client.cookies.set("orion_session", "not-a-jwt")
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()


# -- CSRF -----------------------------------------------------------------


def test_cookie_write_without_a_csrf_token_is_refused(client, logged_in):
    """The attack this opens up: a cross-site form post riding the cookie."""
    r = client.post("/api/keys/", json={"label": "forged"})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_cookie_write_with_a_mismatched_csrf_token_is_refused(client, logged_in):
    r = client.post(
        "/api/keys/",
        json={"label": "forged"},
        headers={"X-CSRF-Token": "guessed-value"},
    )
    assert r.status_code == 403


def test_cookie_write_with_the_matching_token_is_allowed(client, logged_in):
    r = client.post("/api/keys/", json={"label": "legitimate"}, headers=_csrf(client))
    assert r.status_code == 201, r.text


def test_reads_do_not_need_a_csrf_token(client, logged_in):
    """Gating safe methods would break plain navigation for no benefit."""
    assert client.get("/scenarios/").status_code == 200
    assert client.get("/jobs/").status_code == 200


def test_bearer_writes_do_not_need_a_csrf_token(client, account):
    """An SDK client cannot be CSRF'd: the browser never attaches that header.

    Requiring a token there would break every script for no security gain.
    """
    client.cookies.clear()
    token = client.post(
        "/api/auth/login",
        json={
            "identifier": account,
            "password": PASSWORD,
        },
    ).json()["access_token"]
    client.cookies.clear()  # header only, no cookie jar

    r = client.post(
        "/api/keys/",
        json={"label": "sdk-client"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


def test_authorization_header_wins_over_a_stale_cookie(client, account, logged_in):
    """An explicit header names the identity the caller wants."""
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401, "the bad header must not fall back to the cookie"


# -- Token lifetimes ------------------------------------------------------


def test_superadmin_tokens_expire_in_four_hours():
    """A platform-wide credential must not stay valid overnight (D-04)."""
    from arep.api.auth import (
        ACCESS_TOKEN_EXPIRE_HOURS,
        SUPERADMIN_TOKEN_EXPIRE_HOURS,
        token_lifetime_for,
    )

    assert SUPERADMIN_TOKEN_EXPIRE_HOURS == 4
    assert token_lifetime_for("superadmin") == datetime.timedelta(hours=4)
    assert token_lifetime_for("owner") == datetime.timedelta(
        hours=ACCESS_TOKEN_EXPIRE_HOURS
    )


def test_superadmin_jwt_really_carries_the_shorter_expiry():
    """The lifetime helper is only useful if create_access_token consults it."""
    from jose import jwt

    from arep.api.auth import ALGORITHM, SECRET_KEY, create_access_token

    admin = jwt.decode(
        create_access_token({"sub": "1", "role": "superadmin"}),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    owner = jwt.decode(
        create_access_token({"sub": "2", "role": "owner"}),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    assert admin["exp"] < owner["exp"]


def test_cookie_lifetime_matches_the_token(client, account):
    """A cookie outliving its JWT just produces confusing 401s."""
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    session_cookie = [
        h for h in r.headers.get_list("set-cookie") if "orion_session" in h
    ][0]
    assert "Max-Age=86400" in session_cookie  # 24h, the non-superadmin lifetime


def test_cookies_are_not_secure_in_dev(client, account):
    """A Secure cookie is dropped over http://, so dev would never log in."""
    client.cookies.clear()
    r = client.post(
        "/api/auth/login", json={"identifier": account, "password": PASSWORD}
    )
    assert "Secure" not in r.headers.get("set-cookie", "")


def test_cookies_are_secure_outside_dev(monkeypatch):
    from arep.api import auth

    monkeypatch.setenv("ORION_ENV", "production")
    assert auth._cookies_are_secure() is True
    monkeypatch.setenv("ORION_ENV", "dev")
    assert auth._cookies_are_secure() is False
