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
    APIRouter, Depends, File, Form, HTTPException, Request,
    UploadFile, status,
)
from pydantic import BaseModel, Field

from arep.api.auth import get_request_principal
from arep.api.middleware import require_role
from arep.api.model_store import SubmissionType, get_model_store
from arep.database.connection import session_scope
from arep.database.repository import ModelRepository
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
    image: str = Field(..., description="Container registry reference, e.g. registry.orion.run/acme/my-model:v1.0")
    port: int = Field(8080, ge=1, le=65535)


# ── Routes ───────────────────────────────────────────────────────────────

@models_api_router.post(
    "/upload",
    response_model=ModelResponse,
    status_code=201,
    dependencies=[Depends(require_role("owner", "admin", "member"))],
)
async def upload_python_model(
    request: Request,
    name: str = Form(...),
    version: str = Form("v1.0"),
    artefact: UploadFile = File(..., description="cloudpickle-serialised ModelInterface"),
):
    """Upload a cloudpickle-serialised model artefact (Path A — Python SDK)."""
    org_id, user_id, _ = get_request_principal(request)

    pickle_bytes = await artefact.read()
    if not pickle_bytes:
        raise HTTPException(400, "Artefact is empty")
    if len(pickle_bytes) > MAX_PICKLE_BYTES:
        raise HTTPException(
            413, f"Artefact too large: {len(pickle_bytes)} bytes (max {MAX_PICKLE_BYTES})"
        )

    model_id = str(uuid.uuid4())
    store = get_model_store()
    artefact_uri, content_hash, size = store.upload_python_sdk(
        org_id=org_id, model_id=model_id, pickle_bytes=pickle_bytes,
    )

    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.create(
            org_id=org_id, user_id=user_id, name=name, version=version,
            submission_type=SubmissionType.PYTHON_SDK.value,
            artefact_uri=artefact_uri, content_hash=content_hash,
            size_bytes=size, status="ready",
        )
        # Override id to match what we generated, before flush takes the default
        record.id = model_id
        session.flush()
        logger.info(
            "Uploaded SDK model id=%s name=%s@%s org=%s size=%d",
            model_id, name, version, org_id, size,
        )
        return ModelResponse.model_validate(record)


@models_api_router.post(
    "/register",
    response_model=ModelResponse,
    status_code=201,
    dependencies=[Depends(require_role("owner", "admin", "member"))],
)
def register_docker_model(req: RegisterDockerRequest, request: Request):
    """Register a Docker image as a model (Path B — Docker)."""
    org_id, user_id, _ = get_request_principal(request)
    model_id = str(uuid.uuid4())

    store = get_model_store()
    artefact_uri = store.register_docker(
        org_id=org_id, model_id=model_id, image=req.image, port=req.port,
    )

    with session_scope() as session:
        repo = ModelRepository(session)
        record = repo.create(
            org_id=org_id, user_id=user_id, name=req.name, version=req.version,
            submission_type=SubmissionType.DOCKER.value,
            artefact_uri=artefact_uri, status="ready",
        )
        record.id = model_id
        session.flush()
        logger.info(
            "Registered Docker model id=%s name=%s@%s image=%s org=%s",
            model_id, req.name, req.version, req.image, org_id,
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
