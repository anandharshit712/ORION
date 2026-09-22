"""
Superadmin route tests (Phase 0.6, defect D-09).

The admin router grants credits, flips the cloudpickle allowlist and promotes
users — the three things that, if reachable by a tenant, end the product. The
register listed it as untested.

Note the bootstrap: the entire router requires superadmin, including
POST /api/admin/superadmin, so the first one cannot be created through the API.
These tests write the row directly, which is what a deployment does too.
"""

from __future__ import annotations

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


@pytest.fixture(autouse=True)
def clean_cookies(client):
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture(scope="module")
def tenant(client):
    """An ordinary org owner — the role that must never reach these routes."""
    email = "tenant@example.com"
    r = client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "username": "tenantuser",
            "password": PASSWORD,
            "org_name": "Tenant Org",
            "org_slug": "tenant",
        },
    )
    assert r.status_code == 201, r.text
    verify_email_for(email)

    client.cookies.clear()
    r = client.post("/api/auth/login", json={"identifier": email, "password": PASSWORD})
    client.cookies.clear()
    return {
        "org_id": r.json()["org_id"],
        "headers": {"Authorization": f"Bearer {r.json()['access_token']}"},
    }


@pytest.fixture(scope="module")
def admin(client):
    """Bootstrap a superadmin the way a deployment does: straight into the DB."""
    from arep.api.auth import hash_password
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord
    from arep.database.repository import OrganisationRepository

    email = "root@example.com"
    with session_scope() as session:
        org = OrganisationRepository(session).get_or_create_system_org()
        session.add(
            UserRecord(
                org_id=org.id,
                role="superadmin",
                email=email,
                username="root",
                hashed_password=hash_password(PASSWORD),
                email_verified=True,
            )
        )

    client.cookies.clear()
    r = client.post("/api/auth/login", json={"identifier": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"headers": {"Authorization": f"Bearer {r.json()['access_token']}"}}


# -- The gate -------------------------------------------------------------

ADMIN_READS = ["/api/admin/users", "/api/admin/orgs"]


@pytest.mark.parametrize("path", ADMIN_READS)
def test_a_tenant_cannot_read_admin_routes(client, tenant, path):
    assert client.get(path, headers=tenant["headers"]).status_code == 403


@pytest.mark.parametrize("path", ADMIN_READS)
def test_an_anonymous_caller_cannot_read_admin_routes(client, path):
    assert client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("path", ADMIN_READS)
def test_a_superadmin_can(client, admin, path):
    r = client.get(path, headers=admin["headers"])
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# -- Credits --------------------------------------------------------------


def test_a_superadmin_can_top_up_credits(client, admin, tenant):
    before = client.get("/api/orgs/me", headers=tenant["headers"]).json()["run_credits"]

    r = client.post(
        f"/api/admin/orgs/{tenant['org_id']}/credits",
        headers=admin["headers"],
        json={"amount": 25, "note": "beta"},
    )
    assert r.status_code == 200, r.text

    after = client.get("/api/orgs/me", headers=tenant["headers"]).json()["run_credits"]
    assert after == before + 25


def test_a_tenant_cannot_top_up_its_own_credits(client, tenant):
    """The whole billing model rests on this one being 403."""
    before = client.get("/api/orgs/me", headers=tenant["headers"]).json()["run_credits"]

    r = client.post(
        f"/api/admin/orgs/{tenant['org_id']}/credits",
        headers=tenant["headers"],
        json={"amount": 1_000_000},
    )
    assert r.status_code == 403

    after = client.get("/api/orgs/me", headers=tenant["headers"]).json()["run_credits"]
    assert after == before


def test_topping_up_an_unknown_org_is_404(client, admin):
    r = client.post(
        "/api/admin/orgs/not-a-real-org/credits",
        headers=admin["headers"],
        json={"amount": 5},
    )
    assert r.status_code == 404


def test_a_non_positive_top_up_is_rejected(client, admin, tenant):
    """gt=0 on the schema — a negative "top-up" is a silent credit theft."""
    r = client.post(
        f"/api/admin/orgs/{tenant['org_id']}/credits",
        headers=admin["headers"],
        json={"amount": -50},
    )
    assert r.status_code == 422


# -- The cloudpickle allowlist (D-01) -------------------------------------


def test_the_pickle_gate_is_closed_by_default(client, tenant):
    """Arbitrary-code upload must be opt-in, per org, by a human."""
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    with session_scope() as session:
        assert (
            OrganisationRepository(session).allows_pickle_models(tenant["org_id"])
            is False
        )


def test_a_superadmin_can_open_and_close_the_pickle_gate(client, admin, tenant):
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    r = client.put(
        f"/api/admin/orgs/{tenant['org_id']}/pickle-models",
        headers=admin["headers"],
        json={"enabled": True, "note": "design partner"},
    )
    assert r.status_code == 200, r.text

    with session_scope() as session:
        assert (
            OrganisationRepository(session).allows_pickle_models(tenant["org_id"])
            is True
        )

    r = client.put(
        f"/api/admin/orgs/{tenant['org_id']}/pickle-models",
        headers=admin["headers"],
        json={"enabled": False},
    )
    assert r.status_code == 200

    with session_scope() as session:
        assert (
            OrganisationRepository(session).allows_pickle_models(tenant["org_id"])
            is False
        )


def test_a_tenant_cannot_open_its_own_pickle_gate(client, tenant):
    """Otherwise the D-01 gate is decorative."""
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    r = client.put(
        f"/api/admin/orgs/{tenant['org_id']}/pickle-models",
        headers=tenant["headers"],
        json={"enabled": True},
    )
    assert r.status_code == 403

    with session_scope() as session:
        assert (
            OrganisationRepository(session).allows_pickle_models(tenant["org_id"])
            is False
        )


# -- Promotion ------------------------------------------------------------


def test_a_tenant_cannot_promote_itself(client, tenant):
    from arep.database.connection import session_scope
    from arep.database.models import UserRecord

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email="tenant@example.com").first()
        user_id = user.id

    r = client.post(f"/api/admin/users/{user_id}/promote", headers=tenant["headers"])
    assert r.status_code == 403

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(id=user_id).first()
        assert user.role != "superadmin"


def test_promoting_an_unknown_user_is_404(client, admin):
    assert (
        client.post(
            "/api/admin/users/999999/promote", headers=admin["headers"]
        ).status_code
        == 404
    )


def test_a_superadmin_can_create_another_superadmin(client, admin):
    r = client.post(
        "/api/admin/superadmin",
        headers=admin["headers"],
        json={
            "email": "root2@example.com",
            "username": "root2",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "superadmin"


def test_creating_a_duplicate_superadmin_is_409(client, admin):
    r = client.post(
        "/api/admin/superadmin",
        headers=admin["headers"],
        json={
            "email": "root2@example.com",
            "username": "root2",
            "password": PASSWORD,
        },
    )
    assert r.status_code == 409
