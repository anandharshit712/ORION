"""
ORION Superadmin routes.

Routes (all under /api/admin, superadmin-only):
  POST   /api/admin/superadmin              — create new superadmin user (in system org)
  POST   /api/admin/users/{user_id}/promote — promote existing user to superadmin
  POST   /api/admin/users/{user_id}/demote  — demote superadmin back to "owner"
  GET    /api/admin/users                   — list all users across all orgs
  GET    /api/admin/orgs                    — list all organisations

Reads (org_id, user_id, role) from request.state populated by OrgAuthMiddleware.
require_superadmin() gates every route.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from arep.api.auth import hash_password
from arep.api.middleware import require_superadmin
from arep.database.connection import session_scope
from arep.database.models import UserRecord
from arep.database.repository import (
    OrganisationRepository, UserRepository,
)
from arep.utils.logging_config import get_logger

logger = get_logger("api.admin")

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["Superadmin"],
    dependencies=[Depends(require_superadmin())],
)


# ── Schemas ──────────────────────────────────────────────────────────────

class SuperadminCreateRequest(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None


class AdminUserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    role: str
    org_id: Optional[str]
    is_active: bool
    created_at: datetime.datetime
    last_login: Optional[datetime.datetime]

    class Config:
        from_attributes = True


class AdminOrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    run_credits: int
    is_system: bool
    stripe_customer_id: Optional[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# ── Routes ───────────────────────────────────────────────────────────────

@admin_router.post(
    "/superadmin",
    response_model=AdminUserResponse,
    status_code=201,
)
def create_superadmin(req: SuperadminCreateRequest):
    """Create a new superadmin user attached to the system org."""
    if len(req.password) > 72:
        raise HTTPException(400, "Password cannot be longer than 72 characters")

    with session_scope() as session:
        existing = session.query(UserRecord).filter(
            (UserRecord.email == req.email) | (UserRecord.username == req.username)
        ).first()
        if existing is not None:
            raise HTTPException(409, "Email or username already registered")

        org = OrganisationRepository(session).get_or_create_system_org()
        user = UserRecord(
            org_id=org.id,
            role="superadmin",
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        logger.info("Created superadmin user=%s id=%d", user.username, user.id)
        return AdminUserResponse.model_validate(user)


@admin_router.post(
    "/users/{user_id}/promote",
    response_model=AdminUserResponse,
)
def promote_to_superadmin(user_id: int):
    """Promote an existing user to superadmin (re-attaches them to system org)."""
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(404, "User not found")
        sys_org = OrganisationRepository(session).get_or_create_system_org()
        user.role = "superadmin"
        user.org_id = sys_org.id
        session.flush()
        session.refresh(user)
        logger.info("Promoted user id=%d to superadmin", user_id)
        return AdminUserResponse.model_validate(user)


@admin_router.post(
    "/users/{user_id}/demote",
    response_model=AdminUserResponse,
)
def demote_superadmin(user_id: int, request: Request):
    """Demote a superadmin back to owner. Cannot demote yourself."""
    caller_id = getattr(request.state, "user_id", None)
    if caller_id is not None and int(caller_id) == int(user_id):
        raise HTTPException(400, "Cannot demote yourself")
    with session_scope() as session:
        repo = UserRepository(session)
        user = repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(404, "User not found")
        if user.role != "superadmin":
            raise HTTPException(400, "User is not a superadmin")
        user.role = "owner"
        session.flush()
        session.refresh(user)
        logger.info("Demoted superadmin id=%d to owner", user_id)
        return AdminUserResponse.model_validate(user)


@admin_router.get("/users", response_model=List[AdminUserResponse])
def list_all_users():
    with session_scope() as session:
        users = UserRepository(session).list_all()
        return [AdminUserResponse.model_validate(u) for u in users]


@admin_router.get("/orgs", response_model=List[AdminOrgResponse])
def list_all_orgs():
    with session_scope() as session:
        orgs = OrganisationRepository(session).list_all()
        return [AdminOrgResponse.model_validate(o) for o in orgs]
