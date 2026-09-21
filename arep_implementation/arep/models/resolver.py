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
from arep.database.repository import ModelRepository, OrganisationRepository
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
        PermissionError: cloudpickle artefact whose org is not cleared for it.
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
        content_hash = record.content_hash
        submission_type = record.submission_type
        status = record.status
        # Gate on the ORG THAT OWNS THE ARTEFACT, not on the caller's org_id:
        # org_id is optional here, and a None caller must not skip the check.
        pickle_allowed = OrganisationRepository(session).allows_pickle_models(
            record.org_id
        )

    if status != "ready":
        raise RuntimeError(f"Model {name_or_id} not ready (status={status})")

    store = get_model_store()
    if submission_type == SubmissionType.PYTHON_SDK.value:
        if not pickle_allowed:
            # Defence in depth: upload is gated too, but artefacts uploaded
            # before the gate existed must not become runnable.
            raise PermissionError(
                f"Model {name_or_id} uses the cloudpickle path, which is "
                f"disabled for its organisation. Use the Docker submission "
                f"path, or ask an administrator to enable it."
            )
        # Verified against the hash recorded at upload: these bytes are
        # about to be unpickled, and unpickling is code execution.
        pickle_bytes = store.fetch_python_sdk(artefact_uri, content_hash)
        return SubprocessModelRunner(pickle_bytes=pickle_bytes)

    if submission_type == SubmissionType.DOCKER.value:
        image, port = store.get_docker_image(artefact_uri)
        # Phase 2, D-01 step 2. This used to return an HttpModelAdapter pointed
        # at localhost:<port> with a comment saying the caller owned the
        # container lifecycle — and no caller did. A registered Docker model
        # therefore either failed to connect or talked to whatever happened to
        # be listening on that port on the API host, which is worse. The path
        # the pickle gate recommends as the safe one had no boundary at all.
        #
        # ContainerModelRunner starts the image with capabilities dropped, a
        # read-only filesystem, memory/CPU/PID limits, loopback-only publishing
        # and no inherited environment — and under gVisor when configured.
        from arep.models.container import ContainerModelRunner

        return ContainerModelRunner(image=image, port=port, org_id=org_id)

    raise RuntimeError(f"Unsupported submission_type: {submission_type}")
