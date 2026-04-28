"""
ORION Organisations + API Keys routes.

Routes (all under /api):
  GET    /api/orgs/me              — current org details (plan, credits)
  POST   /api/orgs/invite          — owner/admin invite user by email
  GET    /api/keys                 — list API keys (no plaintext)
  POST   /api/keys                 — create API key (plaintext returned ONCE)
  DELETE /api/keys/{key_id}        — revoke key

Reads (org_id, user_id, role) from request.state populated by OrgAuthMiddleware.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from arep.api.auth import (
    OrgSummary, hash_password, get_request_principal, normalise_slug,
)
from arep.api.middleware import generate_api_key, require_role
from arep.database.connection import session_scope
from arep.database.models import UserRecord
from arep.database.repository import (
    ApiKeyRepository, OrganisationRepository,
)
from arep.utils.logging_config import get_logger

logger = get_logger("api.orgs")

orgs_router = APIRouter(prefix="/api/orgs", tags=["Organisations"])
keys_router = APIRouter(prefix="/api/keys", tags=["API Keys"])


# ── Schemas ──────────────────────────────────────────────────────────────

class OrgDetailsResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    run_credits: int
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class InviteRequest(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = Field("member", pattern="^(admin|member|viewer)$")


class InvitedUserResponse(BaseModel):
    id: int
    email: str
    username: str
    role: str
    org_id: str

    class Config:
        from_attributes = True


class ApiKeyCreateRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)


class ApiKeyResponse(BaseModel):
    id: str
    label: str
    key_prefix: str
    last_used_at: Optional[datetime.datetime]
    created_at: datetime.datetime
    revoked_at: Optional[datetime.datetime]

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    plaintext: str = Field(..., description="The plaintext key. Shown ONCE.")


# ── Org routes ───────────────────────────────────────────────────────────

@orgs_router.get("/me", response_model=OrgDetailsResponse)
def get_my_org(request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        org = OrganisationRepository(session).get_by_id(org_id)
        if org is None:
            raise HTTPException(404, "Organisation not found")
        return OrgDetailsResponse.model_validate(org)


@orgs_router.post(
    "/invite",
    response_model=InvitedUserResponse,
    status_code=201,
    dependencies=[Depends(require_role("owner", "admin"))],
)
def invite_user(req: InviteRequest, request: Request):
    """Owner/admin: create a user inside the caller's organisation."""
    org_id, _, _ = get_request_principal(request)
    if len(req.password) > 72:
        raise HTTPException(400, "Password cannot be longer than 72 characters")

    with session_scope() as session:
        existing = session.query(UserRecord).filter(
            (UserRecord.email == req.email) | (UserRecord.username == req.username)
        ).first()
        if existing:
            raise HTTPException(409, "Email or username already registered")

        org = OrganisationRepository(session).get_by_id(org_id)
        if org is None:
            raise HTTPException(404, "Organisation not found")

        user = UserRecord(
            org_id=org.id,
            role=req.role,
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
        )
        session.add(user)
        session.flush()
        logger.info("Invited user=%s role=%s into org=%s", user.username, user.role, org.id)
        return InvitedUserResponse(
            id=user.id, email=user.email, username=user.username,
            role=user.role, org_id=user.org_id,
        )


# ── API key routes ───────────────────────────────────────────────────────

@keys_router.get("/", response_model=List[ApiKeyResponse])
def list_api_keys(request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        keys = ApiKeyRepository(session).list_for_org(org_id)
        return [ApiKeyResponse.model_validate(k) for k in keys]


@keys_router.post(
    "/",
    response_model=ApiKeyCreateResponse,
    status_code=201,
    dependencies=[Depends(require_role("owner", "admin", "member"))],
)
def create_api_key(req: ApiKeyCreateRequest, request: Request):
    """Create an API key. Plaintext returned ONCE — store it securely."""
    org_id, user_id, _ = get_request_principal(request)
    plaintext, key_hash, key_prefix = generate_api_key()
    with session_scope() as session:
        repo = ApiKeyRepository(session)
        record = repo.create(
            org_id=org_id, user_id=user_id, key_hash=key_hash,
            key_prefix=key_prefix, label=req.label,
        )
        session.flush()
        logger.info("Created API key prefix=%s org=%s user=%s", key_prefix, org_id, user_id)
        return ApiKeyCreateResponse(
            id=record.id,
            label=record.label,
            key_prefix=record.key_prefix,
            last_used_at=record.last_used_at,
            created_at=record.created_at,
            revoked_at=record.revoked_at,
            plaintext=plaintext,
        )


@keys_router.delete(
    "/{key_id}",
    status_code=204,
    dependencies=[Depends(require_role("owner", "admin"))],
)
def revoke_api_key(key_id: str, request: Request):
    org_id, _, _ = get_request_principal(request)
    with session_scope() as session:
        ok = ApiKeyRepository(session).revoke(key_id, org_id)
        if not ok:
            raise HTTPException(404, "API key not found")
    return None
