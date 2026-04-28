"""
ORION Authentication Module.

JWT-based authentication with multi-tenancy:
  - POST /api/auth/signup    — create org + first owner user atomically
  - POST /api/auth/register  — alias of signup (legacy name)
  - POST /api/auth/login     — obtain a JWT token (carries org_id + role)
  - GET  /api/auth/me        — current user profile + org details
"""

from __future__ import annotations

import os
import re
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from arep.database.connection import get_session, session_scope
from arep.database.models import UserRecord, OrganisationRecord
from arep.database.repository import OrganisationRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.auth")

# ── Config ───────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("ORION_SECRET_KEY", "orion-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# ── Password hashing ────────────────────────────────────────────────────

import bcrypt

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    pwd_bytes = plain.encode('utf-8')[:72]
    return bcrypt.checkpw(pwd_bytes, hashed.encode('utf-8'))


# ── JWT ──────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode JWT. Raises JWTError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRecord:
    """FastAPI dependency — decode JWT and return the UserRecord."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(str(user_id_str))
    except (JWTError, ValueError):
        raise credentials_exception

    session = get_session()
    try:
        user = session.query(UserRecord).filter(UserRecord.id == user_id).first()
        if user is None:
            raise credentials_exception
        return user
    finally:
        session.close()


def get_request_principal(request: Request) -> tuple[str, int, str]:
    """
    Read (org_id, user_id, role) from request.state populated by OrgAuthMiddleware.
    Raises 401 if unauthenticated.
    """
    org_id = getattr(request.state, "org_id", None)
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    if not org_id or user_id is None or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return org_id, int(user_id), role


# ── Slug helper ─────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def normalise_slug(raw: str) -> str:
    s = _SLUG_RE.sub("-", raw.lower()).strip("-")
    return s[:64] or "org"


# ── Pydantic schemas ────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    org_name: Optional[str] = Field(None, description="Organisation display name")
    org_slug: Optional[str] = Field(None, description="URL-safe organisation slug")


class LoginRequest(BaseModel):
    identifier: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    org_id: str
    role: str


class OrgSummary(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    run_credits: int

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    org_id: Optional[str]
    role: str
    created_at: datetime.datetime
    last_login: Optional[datetime.datetime]
    organisation: Optional[OrgSummary] = None

    class Config:
        from_attributes = True


# ── Router ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _create_user_with_org(req: SignupRequest) -> UserRecord:
    """Atomically create org + first owner user."""
    if len(req.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 characters",
        )
    org_name = req.org_name or req.username
    slug_seed = req.org_slug or req.username
    slug = normalise_slug(slug_seed)

    with session_scope() as session:
        existing = session.query(UserRecord).filter(
            (UserRecord.email == req.email) | (UserRecord.username == req.username)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )

        org_repo = OrganisationRepository(session)
        # Resolve unique slug: append -2, -3, ... if collision.
        candidate = slug
        suffix = 2
        while org_repo.get_by_slug(candidate) is not None:
            candidate = f"{slug}-{suffix}"
            suffix += 1
        org = org_repo.create(name=org_name, slug=candidate, plan="free", run_credits=50)

        user = UserRecord(
            org_id=org.id,
            role="owner",
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        # Eager-load org for response
        _ = user.organisation
        session.expunge(user)
        if user.organisation is not None:
            session.expunge(user.organisation)
        logger.info("Signed up user=%s org=%s slug=%s", user.username, org.id, candidate)
        return user


@auth_router.post("/signup", response_model=UserResponse, status_code=201)
def signup(req: SignupRequest):
    """Create a new organisation and its first owner user."""
    return _create_user_with_org(req)


@auth_router.post("/register", response_model=UserResponse, status_code=201)
def register(req: SignupRequest):
    """Legacy alias of /signup."""
    return _create_user_with_org(req)


@auth_router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate and return a JWT token carrying org_id + role."""
    if len(req.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    session = get_session()
    try:
        user = session.query(UserRecord).filter(
            (UserRecord.email == req.identifier) | (UserRecord.username == req.identifier)
        ).first()
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username/email or password",
            )
        if not user.org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not assigned to an organisation",
            )

        user.last_login = datetime.datetime.utcnow()
        session.commit()

        token = create_access_token(data={
            "sub": str(user.id),
            "email": user.email,
            "org_id": user.org_id,
            "role": user.role,
        })
        logger.info("User logged in: %s (org=%s)", user.username, user.org_id)
        return TokenResponse(
            access_token=token,
            org_id=user.org_id,
            role=user.role,
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@auth_router.get("/me", response_model=UserResponse)
def get_me(current_user: UserRecord = Depends(get_current_user)):
    """Get the currently authenticated user's profile (with org details)."""
    return current_user
