"""
Customer model submission tests (P1.2 SaaS).

Covers:
  - POST /api/models/upload accepts a cloudpickle artefact and returns model_id
  - Listing returns the uploaded model
  - GET /api/models/{id} returns the artefact metadata
  - Org A cannot see/fetch/delete Org B's model
  - DELETE removes the artefact + DB record
  - POST /api/models/register stores Docker image refs
  - Resolver dispatches built-in name → instance, UUID → sandbox/HTTP adapter
"""

from __future__ import annotations

import io
import os
import sys
import tempfile

import pytest

from tests.conftest import verify_email_for

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """Spin up a TestClient + temp model store."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["ORION_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["ORION_MODEL_STORE_PATH"] = str(tmp_path_factory.mktemp("model_store"))

    from arep.database import connection as conn_mod
    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    # Reset ModelStore singleton so it picks up the new path
    from arep.api import model_store as ms
    ms._store = None

    from fastapi.testclient import TestClient
    from arep.api.app import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _set_pickle_gate(slug: str, enabled: bool) -> str:
    """Flip organisations.allow_pickle_models for one org. Returns its id.

    Stands in for the superadmin route PUT /api/admin/orgs/{id}/pickle-models,
    which needs a superadmin token these tests do not mint.
    """
    from arep.database.connection import session_scope
    from arep.database.repository import OrganisationRepository

    with session_scope() as session:
        repo = OrganisationRepository(session)
        org = repo.get_by_slug(slug)
        assert org is not None, f"org {slug!r} not found"
        repo.set_allow_pickle_models(org.id, enabled)
        return org.id


def _signup(client, email, username, slug, allow_pickle=True):
    """Create a user + org.

    Phase 0.2 gates the cloudpickle upload path per org (default OFF), so the
    tests that exercise SDK upload mechanics enable it explicitly — as a
    superadmin would for a design partner. Pass allow_pickle=False to test the
    default-denied behaviour itself.
    """
    r = client.post("/api/auth/signup", json={
        "email": email, "username": username,
        "password": "password123", "org_slug": slug,
    })
    assert r.status_code == 201, r.text
    # D-04: an unverified account cannot upload or register a model. These tests
    # are about the artefact paths, not the verification flow.
    verify_email_for(email)
    if allow_pickle:
        _set_pickle_gate(slug, True)
    return r.json()


def _login(client, identifier):
    r = client.post("/api/auth/login", json={
        "identifier": identifier, "password": "password123",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_pickle_blob() -> bytes:
    """Cloudpickle a real ModelInterface instance."""
    import cloudpickle
    from arep.models.examples.example_models import EmergencyBrakeModel
    return cloudpickle.dumps(EmergencyBrakeModel())


# ── Tests ────────────────────────────────────────────────────────────────

def test_upload_python_sdk_model(env):
    _signup(env, "owen@a.com", "owen", "owen-co")
    token = _login(env, "owen")
    blob = _make_pickle_blob()

    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "brake-model", "version": "v1.0"},
        files={"artefact": ("brake.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "brake-model"
    assert body["version"] == "v1.0"
    assert body["submission_type"] == "python_sdk"
    assert body["status"] == "ready"
    assert body["size_bytes"] == len(blob)
    assert body["content_hash"]
    assert body["id"]


def test_upload_rejects_empty_artefact(env):
    _signup(env, "petra@a.com", "petra", "petra-co")
    token = _login(env, "petra")

    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "x", "version": "v1.0"},
        files={"artefact": ("x.pkl", io.BytesIO(b""), "application/octet-stream")},
    )
    assert r.status_code == 400


def test_list_models_org_scoped(env):
    _signup(env, "quinn@a.com", "quinn", "quinn-co")
    _signup(env, "rita@a.com", "rita", "rita-co")
    tq = _login(env, "quinn")
    tr = _login(env, "rita")

    blob = _make_pickle_blob()
    env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {tq}"},
        data={"name": "quinn-model", "version": "v1.0"},
        files={"artefact": ("a.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {tr}"},
        data={"name": "rita-model", "version": "v1.0"},
        files={"artefact": ("b.pkl", io.BytesIO(blob), "application/octet-stream")},
    )

    listed_q = env.get("/api/models/", headers={"Authorization": f"Bearer {tq}"}).json()
    listed_r = env.get("/api/models/", headers={"Authorization": f"Bearer {tr}"}).json()
    names_q = {m["name"] for m in listed_q}
    names_r = {m["name"] for m in listed_r}
    assert "quinn-model" in names_q
    assert "rita-model" not in names_q
    assert "rita-model" in names_r
    assert "quinn-model" not in names_r


def test_cross_org_model_get_returns_404(env):
    _signup(env, "sam@a.com", "sam", "sam-co")
    _signup(env, "tom@a.com", "tom", "tom-co")
    ts = _login(env, "sam")
    tt = _login(env, "tom")

    blob = _make_pickle_blob()
    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {ts}"},
        data={"name": "sam-secret", "version": "v1.0"},
        files={"artefact": ("a.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    sam_id = r.json()["id"]

    # Tom tries to fetch + delete Sam's model
    r = env.get(f"/api/models/{sam_id}", headers={"Authorization": f"Bearer {tt}"})
    assert r.status_code == 404
    r = env.delete(f"/api/models/{sam_id}", headers={"Authorization": f"Bearer {tt}"})
    assert r.status_code == 404


def test_delete_model(env):
    _signup(env, "una@a.com", "una", "una-co")
    token = _login(env, "una")
    blob = _make_pickle_blob()
    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "tmp", "version": "v1.0"},
        files={"artefact": ("tmp.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    model_id = r.json()["id"]

    r = env.delete(f"/api/models/{model_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204

    r = env.get(f"/api/models/{model_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_register_docker_model(env):
    _signup(env, "victor@a.com", "victor", "victor-co")
    token = _login(env, "victor")

    r = env.post(
        "/api/models/register",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "vic-docker", "version": "v2.0",
            "image": "registry.local/victor/model:v2", "port": 9090,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["submission_type"] == "docker"
    assert body["artefact_uri"].startswith("docker://")


def test_resolver_builtin_name(env):
    """Resolver returns built-in instance for known names without DB lookup."""
    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model
    model = resolve_model("EmergencyBrake", AVAILABLE_MODELS, org_id=None)
    assert hasattr(model, "predict")


def test_resolver_invalid_name(env):
    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model
    with pytest.raises(ValueError):
        resolve_model("NotAModel", AVAILABLE_MODELS, org_id=None)


def test_resolver_uuid_not_found(env):
    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model
    with pytest.raises(KeyError):
        resolve_model(
            "00000000-0000-0000-0000-000000000000",
            AVAILABLE_MODELS, org_id="bogus-org",
        )


def test_resolver_uuid_dispatches_to_sandbox(env):
    """Upload a model, resolve its UUID, get a SubprocessModelRunner."""
    _signup(env, "wade@a.com", "wade", "wade-co")
    token = _login(env, "wade")
    blob = _make_pickle_blob()
    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "wade-model", "version": "v1.0"},
        files={"artefact": ("w.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    model_id = r.json()["id"]

    # Find the org_id by reading /api/orgs/me
    org_id = env.get(
        "/api/orgs/me", headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model
    from arep.models.sandbox import SubprocessModelRunner

    instance = resolve_model(model_id, AVAILABLE_MODELS, org_id=org_id)
    assert isinstance(instance, SubprocessModelRunner)
    instance.close()  # clean up subprocess


def test_resolver_uuid_org_mismatch_blocked(env):
    """Even if model UUID is valid, wrong org cannot resolve it."""
    _signup(env, "xan@a.com", "xan", "xan-co")
    _signup(env, "yael@a.com", "yael", "yael-co")
    token_x = _login(env, "xan")
    token_y = _login(env, "yael")

    blob = _make_pickle_blob()
    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token_x}"},
        data={"name": "xan-model", "version": "v1.0"},
        files={"artefact": ("x.pkl", io.BytesIO(blob), "application/octet-stream")},
    )
    model_id = r.json()["id"]

    yael_org_id = env.get(
        "/api/orgs/me", headers={"Authorization": f"Bearer {token_y}"},
    ).json()["id"]

    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model

    with pytest.raises(KeyError):
        resolve_model(model_id, AVAILABLE_MODELS, org_id=yael_org_id)


# ── Phase 0.2 — per-org cloudpickle gate (D-01) ──────────────────────────

def test_upload_blocked_when_org_not_cleared_for_pickle_models(env):
    """Default-deny: a self-serve org cannot upload a cloudpickle artefact."""
    _signup(env, "zoe@a.com", "zoe", "zoe-co", allow_pickle=False)
    token = _login(env, "zoe")

    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "sneaky", "version": "v1.0"},
        files={"artefact": ("s.pkl", io.BytesIO(_make_pickle_blob()),
                            "application/octet-stream")},
    )
    assert r.status_code == 403, r.text
    assert "disabled for this organisation" in r.json()["detail"]


def test_upload_succeeds_once_an_admin_enables_the_path(env):
    _signup(env, "abe@a.com", "abe", "abe-co", allow_pickle=False)
    token = _login(env, "abe")
    files = {"artefact": ("a.pkl", io.BytesIO(_make_pickle_blob()),
                          "application/octet-stream")}

    blocked = env.post(
        "/api/models/upload", headers={"Authorization": f"Bearer {token}"},
        data={"name": "abe-model", "version": "v1.0"}, files=files,
    )
    assert blocked.status_code == 403

    _set_pickle_gate("abe-co", True)
    allowed = env.post(
        "/api/models/upload", headers={"Authorization": f"Bearer {token}"},
        data={"name": "abe-model", "version": "v1.0"},
        files={"artefact": ("a.pkl", io.BytesIO(_make_pickle_blob()),
                            "application/octet-stream")},
    )
    assert allowed.status_code == 201, allowed.text


def test_resolver_refuses_pickle_model_after_the_gate_is_revoked(env):
    """
    Artefacts uploaded while the gate was open must stop being runnable when it
    closes — otherwise revoking access to a compromised tenant does nothing.
    """
    _signup(env, "bea@a.com", "bea", "bea-co")
    token = _login(env, "bea")
    r = env.post(
        "/api/models/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"name": "bea-model", "version": "v1.0"},
        files={"artefact": ("b.pkl", io.BytesIO(_make_pickle_blob()),
                            "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    model_id = r.json()["id"]

    org_id = _set_pickle_gate("bea-co", False)

    from arep.api.routes import AVAILABLE_MODELS
    from arep.models.resolver import resolve_model

    with pytest.raises(PermissionError):
        resolve_model(model_id, AVAILABLE_MODELS, org_id=org_id)

    # ...and an unscoped caller cannot slip past it either
    with pytest.raises(PermissionError):
        resolve_model(model_id, AVAILABLE_MODELS, org_id=None)


# -- Artefact integrity (Phase 2, closing the model_store TODO) ----------

def test_a_tampered_artefact_is_refused(tmp_path):
    """These bytes get unpickled, and unpickling is code execution. The
    sandbox contains what the code does once running; the hash check is what
    notices the bytes are not the ones the customer uploaded."""
    from arep.api.model_store import ModelArtefactError, ModelStore

    store = ModelStore()
    blob = b"the original artefact"
    path = tmp_path / "model.pkl"
    path.write_bytes(blob)
    uri = f"file://{path}"
    recorded = store.compute_hash(blob)

    # Unchanged: loads fine.
    assert store.fetch_python_sdk(uri, recorded) == blob

    # Replaced on disk without touching the API — storage is not a trust
    # boundary, and a shared volume or bucket can be written by other things.
    path.write_bytes(b"something else entirely")
    with pytest.raises(ModelArtefactError, match="hash mismatch"):
        store.fetch_python_sdk(uri, recorded)


def test_fetching_without_a_hash_still_works_but_warns(tmp_path, caplog):
    """Callers that predate the check keep working; the warning is what makes
    the gap visible rather than silent."""
    import logging

    from arep.api.model_store import ModelStore

    store = ModelStore()
    path = tmp_path / "model.pkl"
    path.write_bytes(b"unverified")

    with caplog.at_level(logging.WARNING):
        assert store.fetch_python_sdk(f"file://{path}") == b"unverified"

    assert any("without a hash check" in record.message for record in caplog.records)


def test_the_resolver_passes_the_recorded_hash():
    """The resolver holds the record, so it has no excuse not to verify."""
    import inspect

    from arep.models import resolver

    source = inspect.getsource(resolver.resolve_model)
    assert "fetch_python_sdk(artefact_uri, content_hash)" in source


def test_a_malformed_s3_uri_is_rejected():
    from arep.api.model_store import ModelStore

    with pytest.raises(ValueError, match="Unsupported artefact URI scheme"):
        ModelStore().fetch_python_sdk("ftp://somewhere/model.pkl")
