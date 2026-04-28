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


def _signup(client, email, username, slug):
    r = client.post("/api/auth/signup", json={
        "email": email, "username": username,
        "password": "password123", "org_slug": slug,
    })
    assert r.status_code == 201, r.text
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
