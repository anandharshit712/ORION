"""
ORION Superadmin routes.

Routes (all under /api/admin, superadmin-only):
  POST   /api/admin/superadmin              — create new superadmin user (in system org)
  POST   /api/admin/users/{user_id}/promote — promote existing user to superadmin
  POST   /api/admin/users/{user_id}/demote  — demote superadmin back to "owner"
  GET    /api/admin/users                   — list all users across all orgs
  GET    /api/admin/orgs                    — list all organisations
  POST   /api/admin/orgs/{org_id}/credits   — manually top up an org's run credits (beta)
  PUT    /api/admin/orgs/{org_id}/plan       — change an org's plan

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


# ── Beta credit management ────────────────────────────────────────────────

class CreditTopUpRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Number of credits to add")
    note: Optional[str] = Field(None, description="Internal note for audit trail")


class CreditTopUpResponse(BaseModel):
    org_id: str
    credits_added: int
    new_balance: int
    note: Optional[str]


class PlanChangeRequest(BaseModel):
    plan: str = Field(..., description="beta | free | starter | pro | enterprise")
    set_credits: Optional[int] = Field(
        None,
        description="Optionally override credit balance after plan change",
    )


@admin_router.post(
    "/orgs/{org_id}/credits",
    response_model=CreditTopUpResponse,
    summary="Manually top up an org's run credits",
    description=(
        "Add run credits to any org. Intended for beta user management — "
        "lets you keep testers running without a live Stripe integration. "
        "All top-ups are logged at INFO level for auditing."
    ),
)
def topup_org_credits(org_id: str, req: CreditTopUpRequest, request: Request):
    """Add `amount` run credits to the specified org."""
    caller_id = getattr(request.state, "user_id", None)

    with session_scope() as session:
        repo = OrganisationRepository(session)
        org = repo.get_by_id(org_id)
        if org is None:
            raise HTTPException(404, f"Organisation {org_id!r} not found")

        repo.add_credits(org_id, req.amount)
        session.flush()
        session.refresh(org)
        new_balance = org.run_credits

    logger.info(
        "Admin credit top-up: org=%s added=%d new_balance=%d caller=%s note=%r",
        org_id, req.amount, new_balance, caller_id, req.note,
    )
    return CreditTopUpResponse(
        org_id=org_id,
        credits_added=req.amount,
        new_balance=new_balance,
        note=req.note,
    )


@admin_router.put(
    "/orgs/{org_id}/plan",
    response_model=AdminOrgResponse,
    summary="Change an org's plan",
    description=(
        "Update an org's plan and optionally override its credit balance. "
        "Useful for manually upgrading beta users to a paid tier."
    ),
)
def change_org_plan(org_id: str, req: PlanChangeRequest):
    """Change the plan for an org, optionally setting a new credit balance."""
    valid_plans = {"beta", "free", "starter", "pro", "enterprise"}
    if req.plan not in valid_plans:
        raise HTTPException(400, f"Invalid plan. Must be one of: {sorted(valid_plans)}")

    with session_scope() as session:
        repo = OrganisationRepository(session)
        org = repo.get_by_id(org_id)
        if org is None:
            raise HTTPException(404, f"Organisation {org_id!r} not found")

        org.plan = req.plan
        if req.set_credits is not None:
            if req.set_credits < -1:
                raise HTTPException(400, "set_credits must be -1 (unlimited) or >= 0")
            org.run_credits = req.set_credits

        session.flush()
        session.refresh(org)
        logger.info(
            "Admin plan change: org=%s plan=%s credits=%s",
            org_id, req.plan, org.run_credits,
        )
        return AdminOrgResponse.model_validate(org)
