"""
ORION Model Resolver.

Resolves a model name or UUID to a runnable ``ModelInterface`` instance.

Resolution order:
  1. If the value matches a built-in name (``ConstantAction``, etc.) → instantiate.
  2. If the value parses as a UUID → look up ``ModelRecord``, scope by org_id,
     dispatch to sandbox (python_sdk) or http_adapter (docker).
  3. Else → ``ValueError``.

Org scoping is enforced when ``org_id`` is supplied: a UUID belonging to
another org returns ``KeyError`` ("model not found"), preventing cross-org
model usage.
"""

from __future__ import annotations

import re
from typing import Optional

from arep.api.model_store import get_model_store, SubmissionType
from arep.database.connection import session_scope
from arep.database.repository import ModelRepository
from arep.models.http_adapter import HttpModelAdapter
from arep.models.interface import ModelInterface
from arep.models.sandbox import SubprocessModelRunner
from arep.utils.logging_config import get_logger

logger = get_logger("models.resolver")

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def resolve_model(
    name_or_id: str,
    builtin_registry: dict,
    org_id: Optional[str] = None,
) -> ModelInterface:
    """Resolve a model name or UUID to a runnable ModelInterface.

    Args:
        name_or_id: Built-in model name OR a model UUID.
        builtin_registry: ``AVAILABLE_MODELS`` dict from ``api/routes.py``.
        org_id: If set, customer-model UUID lookup is scoped to this org.

    Raises:
        ValueError: name not in registry and not a UUID.
        KeyError: UUID not found (or belongs to another org).
        RuntimeError: artefact unavailable or unsupported submission type.
    """
    if name_or_id in builtin_registry:
        return builtin_registry[name_or_id]()

    if not is_uuid(name_or_id):
        raise ValueError(
            f"Unknown model: {name_or_id!r}. "
            f"Available built-ins: {list(builtin_registry.keys())} "
            f"or pass a model UUID."
        )

    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.get(name_or_id, org_id=org_id)
        if record is None:
            raise KeyError(f"Model not found: {name_or_id}")
        artefact_uri = record.artefact_uri
        submission_type = record.submission_type
        status = record.status

    if status != "ready":
        raise RuntimeError(f"Model {name_or_id} not ready (status={status})")

    store = get_model_store()
    if submission_type == SubmissionType.PYTHON_SDK.value:
        pickle_bytes = store.fetch_python_sdk(artefact_uri)
        return SubprocessModelRunner(pickle_bytes=pickle_bytes)

    if submission_type == SubmissionType.DOCKER.value:
        image, port = store.get_docker_image(artefact_uri)
        # Caller is responsible for container lifecycle; we assume the
        # container is already reachable on localhost:<port>.
        return HttpModelAdapter(base_url=f"http://localhost:{port}")

    raise RuntimeError(f"Unsupported submission_type: {submission_type}")
