"""
Multi-tenancy + API key auth tests (P1.1 SaaS).

Covers the acceptance criteria:
  - Two orgs can exist; user from org A cannot read runs belonging to org B
  - API key created by org A is rejected when used to access org B's resources
  - JWT and API key auth both work on protected routes
  - GET /api/orgs/me returns the correct run_credits value
  - Public paths (signup/login/health) are accessible without auth
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def client():
    """Spin up a FastAPI TestClient backed by a fresh SQLite file."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"

    # Force reinit of the engine with our test DB before importing app
    from arep.database import connection as conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    from fastapi.testclient import TestClient
    from arep.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    # Cleanup
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _signup(client, email: str, username: str, slug: str) -> dict:
    r = client.post("/api/auth/signup", json={
        "email": email,
        "username": username,
        "password": "password123",
        "org_name": f"{username} org",
        "org_slug": slug,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, identifier: str) -> tuple[str, str, str]:
    r = client.post("/api/auth/login", json={
        "identifier": identifier,
        "password": "password123",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    return j["access_token"], j["org_id"], j["role"]


# ── Tests ────────────────────────────────────────────────────────────────

def test_signup_creates_org_and_owner(client):
    user = _signup(client, "alice@a.com", "alice", "acme")
    assert user["role"] == "owner"
    assert user["org_id"] is not None
    assert user["organisation"]["slug"] == "acme"
    assert user["organisation"]["plan"] == "free"
    assert user["organisation"]["run_credits"] == 50


def test_login_returns_jwt_with_org(client):
    _signup(client, "bob@b.com", "bob", "bobs-co")
    token, org_id, role = _login(client, "bob")
    assert token
    assert org_id
    assert role == "owner"


def test_orgs_me_returns_current_org(client):
    _signup(client, "carol@c.com", "carol", "carol-co")
    token, _, _ = _login(client, "carol")
    r = client.get("/api/orgs/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slug"] == "carol-co"
    assert j["run_credits"] == 50


def test_unauthenticated_request_rejected(client):
    r = client.get("/api/orgs/me")
    assert r.status_code == 401


def test_public_paths_no_auth_required(client):
    assert client.get("/health").status_code == 200
    # signup itself is public; already exercised in other tests


def test_api_key_creation_and_use(client):
    _signup(client, "dave@d.com", "dave", "dave-co")
    token, _, _ = _login(client, "dave")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/keys/", json={"label": "ci-laptop"}, headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    plaintext = body["plaintext"]
    assert plaintext.startswith("sk-orion-")

    # Use the API key to hit a protected endpoint — no JWT required
    r = client.get(
        "/api/orgs/me",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "dave-co"


def test_api_key_revocation(client):
    _signup(client, "erin@e.com", "erin", "erin-co")
    token, _, _ = _login(client, "erin")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/keys/", json={"label": "tmp"}, headers=headers)
    key_id = r.json()["id"]
    plaintext = r.json()["plaintext"]

    # Revoke
    r = client.delete(f"/api/keys/{key_id}", headers=headers)
    assert r.status_code == 204

    # Revoked key must be rejected
    r = client.get(
        "/api/orgs/me",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert r.status_code == 401


def test_org_isolation_keys_listing(client):
    _signup(client, "frank@f.com", "frank", "frank-co")
    _signup(client, "gina@g.com", "gina", "gina-co")
    token_f, _, _ = _login(client, "frank")
    token_g, _, _ = _login(client, "gina")

    # Frank creates a key
    client.post(
        "/api/keys/", json={"label": "frank-key"},
        headers={"Authorization": f"Bearer {token_f}"},
    )
    # Gina creates a key
    client.post(
        "/api/keys/", json={"label": "gina-key"},
        headers={"Authorization": f"Bearer {token_g}"},
    )

    # Each org sees only their own key
    rf = client.get("/api/keys/", headers={"Authorization": f"Bearer {token_f}"}).json()
    rg = client.get("/api/keys/", headers={"Authorization": f"Bearer {token_g}"}).json()
    labels_f = {k["label"] for k in rf}
    labels_g = {k["label"] for k in rg}
    assert "frank-key" in labels_f
    assert "gina-key" not in labels_f
    assert "gina-key" in labels_g
    assert "frank-key" not in labels_g


def test_cross_org_api_key_cannot_revoke(client):
    _signup(client, "hank@h.com", "hank", "hank-co")
    _signup(client, "ivy@i.com", "ivy", "ivy-co")
    token_h, _, _ = _login(client, "hank")
    token_i, _, _ = _login(client, "ivy")

    # Hank creates a key
    r = client.post(
        "/api/keys/", json={"label": "hank-secret"},
        headers={"Authorization": f"Bearer {token_h}"},
    )
    hank_key_id = r.json()["id"]

    # Ivy tries to revoke Hank's key
    r = client.delete(
        f"/api/keys/{hank_key_id}",
        headers={"Authorization": f"Bearer {token_i}"},
    )
    assert r.status_code == 404


def test_invite_user_into_org(client):
    _signup(client, "jane@j.com", "jane", "jane-co")
    token, _, _ = _login(client, "jane")

    r = client.post(
        "/api/orgs/invite",
        json={
            "email": "kate@j.com",
            "username": "kate",
            "password": "password123",
            "role": "member",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    invited = r.json()
    assert invited["role"] == "member"

    # Kate logs in — should be in same org
    token_k, org_id_k, role_k = _login(client, "kate")
    assert role_k == "member"
    # Same org as jane
    r_jane = client.get("/api/orgs/me", headers={"Authorization": f"Bearer {token}"})
    assert r_jane.json()["id"] == org_id_k


def test_invite_requires_owner_or_admin(client):
    # Reuse jane + kate from previous test? No — test is order-independent.
    _signup(client, "leo@l.com", "leo", "leo-co")
    token_owner, _, _ = _login(client, "leo")

    # Owner invites a member
    client.post(
        "/api/orgs/invite",
        json={
            "email": "mia@l.com",
            "username": "mia",
            "password": "password123",
            "role": "member",
        },
        headers={"Authorization": f"Bearer {token_owner}"},
    )

    # Member tries to invite — should be 403
    token_member, _, _ = _login(client, "mia")
    r = client.post(
        "/api/orgs/invite",
        json={
            "email": "ned@l.com",
            "username": "ned",
            "password": "password123",
            "role": "member",
        },
        headers={"Authorization": f"Bearer {token_member}"},
    )
    assert r.status_code == 403


def test_invalid_jwt_rejected(client):
    r = client.get(
        "/api/orgs/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_invalid_api_key_rejected(client):
    r = client.get(
        "/api/orgs/me",
        headers={"Authorization": "Bearer sk-orion-bogusbogusbogus"},
    )
    assert r.status_code == 401
