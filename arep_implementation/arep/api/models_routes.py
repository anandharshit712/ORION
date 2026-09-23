"""
ORION Customer Models API.

Routes:
  POST   /api/models/upload      multipart cloudpickle blob
  POST   /api/models/register    docker image registration
  GET    /api/models/            list org's models
  GET    /api/models/{model_id}  fetch one model
  DELETE /api/models/{model_id}  remove model

All routes are org-scoped via OrgAuthMiddleware. Customer artefacts
never cross org boundaries.
"""

from __future__ import annotations

import datetime
import uuid
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field

from arep.api.auth import require_verified_email, get_request_principal
from arep.api.middleware import require_role
from arep.api.model_store import SubmissionType, get_model_store
from arep.database.models import RunRecord
from arep.database.connection import session_scope
from arep.database.repository import ModelRepository, OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.models")

models_api_router = APIRouter(prefix="/api/models", tags=["Customer Models"])

MAX_PICKLE_BYTES = 64 * 1024 * 1024  # 64 MB cap on uploaded model artefact


# ── Schemas ──────────────────────────────────────────────────────────────


class ModelResponse(BaseModel):
    id: str
    org_id: str
    name: str
    version: str
    submission_type: str
    artefact_uri: str
    content_hash: Optional[str]
    size_bytes: Optional[int]
    status: str
    error: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class RegisterDockerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field("v1.0", min_length=1, max_length=32)
    image: str = Field(
        ...,
        description="Container registry reference, e.g. registry.orion.run/acme/my-model:v1.0",
    )
    port: int = Field(8080, ge=1, le=65535)


# ── Routes ───────────────────────────────────────────────────────────────


@models_api_router.post(
    "/upload",
    response_model=ModelResponse,
    status_code=201,
    dependencies=[
        Depends(require_role("owner", "admin", "member")),
        Depends(require_verified_email),
    ],
)
async def upload_python_model(
    request: Request,
    name: str = Form(...),
    version: str = Form("v1.0"),
    artefact: UploadFile = File(
        ..., description="cloudpickle-serialised ModelInterface"
    ),
):
    """Upload a cloudpickle-serialised model artefact (Path A — Python SDK)."""
    org_id, user_id, _ = get_request_principal(request)

    # Phase 0.2 / D-01: unpickling runs arbitrary customer code, so the SDK
    # path is opt-in per org. Checked before the bytes are stored, not just
    # before they are run.
    with session_scope() as session:
        if not OrganisationRepository(session).allows_pickle_models(org_id):
            raise HTTPException(
                403,
                "The Python SDK (cloudpickle) upload path is disabled for this "
                "organisation. Use POST /api/models/register with a Docker image, "
                "or contact support to have it enabled.",
            )

    pickle_bytes = await artefact.read()
    if not pickle_bytes:
        raise HTTPException(400, "Artefact is empty")
    if len(pickle_bytes) > MAX_PICKLE_BYTES:
        raise HTTPException(
            413,
            f"Artefact too large: {len(pickle_bytes)} bytes (max {MAX_PICKLE_BYTES})",
        )

    model_id = str(uuid.uuid4())
    store = get_model_store()
    artefact_uri, content_hash, size = store.upload_python_sdk(
        org_id=org_id,
        model_id=model_id,
        pickle_bytes=pickle_bytes,
    )

    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.create(
            org_id=org_id,
            user_id=user_id,
            name=name,
            version=version,
            submission_type=SubmissionType.PYTHON_SDK.value,
            artefact_uri=artefact_uri,
            content_hash=content_hash,
            size_bytes=size,
            status="ready",
        )
        # Override id to match what we generated, before flush takes the default
        record.id = model_id
        session.flush()
        logger.info(
            "Uploaded SDK model id=%s name=%s@%s org=%s size=%d",
            model_id,
            name,
            version,
            org_id,
            size,
        )
        return ModelResponse.model_validate(record)


@models_api_router.post(
    "/register",
    response_model=ModelResponse,
    status_code=201,
    dependencies=[
        Depends(require_role("owner", "admin", "member")),
        Depends(require_verified_email),
    ],
)
def register_docker_model(req: RegisterDockerRequest, request: Request):
    """Register a Docker image as a model (Path B — Docker)."""
    org_id, user_id, _ = get_request_principal(request)
    model_id = str(uuid.uuid4())

    store = get_model_store()
    artefact_uri = store.register_docker(
        org_id=org_id,
        model_id=model_id,
        image=req.image,
        port=req.port,
    )

    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.create(
            org_id=org_id,
            user_id=user_id,
            name=req.name,
            version=req.version,
            submission_type=SubmissionType.DOCKER.value,
            artefact_uri=artefact_uri,
            status="ready",
        )
        record.id = model_id
        session.flush()
        logger.info(
            "Registered Docker model id=%s name=%s@%s image=%s org=%s",
            model_id,
            req.name,
            req.version,
            req.image,
            org_id,
        )
        return ModelResponse.model_validate(record)


@models_api_router.get("/", response_model=List[ModelResponse])
def list_models(request: Request):
    """List all models in the caller's organisation."""
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        records = ModelRepository(session).list_for_org(org_id)
        return [ModelResponse.model_validate(r) for r in records]


@models_api_router.get("/{model_id}", response_model=ModelResponse)
def get_model(model_id: str, request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        record = ModelRepository(session).get(model_id, org_id=org_id)
        if record is None:
            raise HTTPException(404, "Model not found")
        return ModelResponse.model_validate(record)


@models_api_router.delete(
    "/{model_id}",
    status_code=204,
    dependencies=[Depends(require_role("owner", "admin"))],
)
def delete_model(model_id: str, request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.get(model_id, org_id=org_id)
        if record is None:
            raise HTTPException(404, "Model not found")
        artefact_uri = record.artefact_uri
        submission_type = record.submission_type
        repo.delete(model_id, org_id=org_id)
    # Best-effort artefact cleanup outside DB tx
    if submission_type == SubmissionType.PYTHON_SDK.value:
        get_model_store().delete(artefact_uri)
    return None


class ModelVersionHistoryEntry(BaseModel):
    """One submitted version of a model, with how it scored (Phase 3.4)."""

    model_id: str
    version: str
    submission_type: str
    status: str
    created_at: datetime.datetime

    runs: int = 0
    composite_mean: Optional[float] = None
    safety_mean: Optional[float] = None
    collision_rate: Optional[float] = None

    # Change against the previous version. None on the first version, and on any
    # version with no scored runs to compare.
    composite_delta: Optional[float] = None
    is_regression: bool = False


class ModelHistoryResponse(BaseModel):
    name: str
    versions: List[ModelVersionHistoryEntry]
    latest_version: Optional[str] = None
    # True when the newest scored version regressed against the one before it.
    has_regression: bool = False


# A composite drop beyond this between consecutive versions is a regression.
# Same threshold RegressionDetector uses, imported rather than restated so the
# dashboard and the CLI cannot disagree about what counts as one.
def _composite_threshold() -> float:
    from arep.analysis.regression_detector import REGRESSION_COMPOSITE_THRESHOLD

    return REGRESSION_COMPOSITE_THRESHOLD


@models_api_router.get("/{name}/history", response_model=ModelHistoryResponse)
def get_model_history(name: str, request: Request):
    """Score trend across every submitted version of one model name (3.4).

    Runs reference a submitted model by its UUID, not by name, so this walks
    name -> versions -> that version's runs. Built-in models are referenced by
    name directly and have no versions, so they are not covered here.

    A version with no runs is still listed. "Uploaded but never evaluated" is a
    real state and hiding it would make a submission look lost.
    """
    org_id, _, _ = get_request_principal(request)

    with session_scope() as session:
        records = [
            m for m in ModelRepository(session).list_for_org(org_id) if m.name == name
        ]
        if not records:
            raise HTTPException(404, f"No model named {name!r} in this organisation")

        # Oldest first: a trend reads forwards, and the delta is against the
        # version before it.
        records.sort(key=lambda m: (m.created_at, m.version))

        entries: List[ModelVersionHistoryEntry] = []
        previous_composite: Optional[float] = None
        threshold = _composite_threshold()

        for record in records:
            runs = (
                session.query(RunRecord).filter(RunRecord.model_name == record.id).all()
            )

            composite = safety = collision_rate = None
            if runs:
                composite = sum(r.composite_score for r in runs) / len(runs)
                safety = sum(r.safety_score for r in runs) / len(runs)
                collision_rate = sum(1 for r in runs if r.collision_occurred) / len(
                    runs
                )

            delta = None
            regressed = False
            if composite is not None and previous_composite is not None:
                delta = composite - previous_composite
                regressed = delta < -threshold

            entries.append(
                ModelVersionHistoryEntry(
                    model_id=record.id,
                    version=record.version,
                    submission_type=record.submission_type,
                    status=record.status,
                    created_at=record.created_at,
                    runs=len(runs),
                    composite_mean=composite,
                    safety_mean=safety,
                    collision_rate=collision_rate,
                    composite_delta=delta,
                    is_regression=regressed,
                )
            )

            # Only advance the baseline on a version that was actually scored,
            # so an unevaluated submission does not break the chain and make the
            # next real version look like the first.
            if composite is not None:
                previous_composite = composite

        scored = [e for e in entries if e.composite_mean is not None]
        return ModelHistoryResponse(
            name=name,
            versions=entries,
            latest_version=entries[-1].version if entries else None,
            has_regression=bool(scored and scored[-1].is_regression),
        )
