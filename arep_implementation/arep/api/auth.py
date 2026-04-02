"""
ORION Authentication Module.

JWT-based authentication with:
  - POST /api/auth/register  — create an account
  - POST /api/auth/login     — obtain a JWT token
  - GET  /api/auth/me        — get current user profile
"""

from __future__ import annotations

import os
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field

from arep.database.connection import get_session
from arep.database.models import UserRecord
from arep.utils.logging_config import get_logger

logger = get_logger("api.auth")

# ── Config ───────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("ORION_SECRET_KEY", "orion-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# ── Password hashing ────────────────────────────────────────────────────

import bcrypt

def hash_password(password: str) -> str:
    # bcrypt throws ValueError if > 72 bytes. We safely truncate.
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


def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRecord:
    """FastAPI dependency — decode JWT and return the UserRecord."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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


# ── Pydantic schemas ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime.datetime
    last_login: Optional[datetime.datetime]

    class Config:
        from_attributes = True


# ── Router ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@auth_router.post("/register", response_model=UserResponse, status_code=201)
def register(req: RegisterRequest):
    """Create a new user account."""
    if len(req.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 characters",
        )
    session = get_session()
    try:
        # Check duplicates
        existing = session.query(UserRecord).filter(
            (UserRecord.email == req.email) | (UserRecord.username == req.username)
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email or username already registered",
            )

        user = UserRecord(
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("New user registered: %s", user.username)
        return user
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@auth_router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate and return a JWT token."""
    if len(req.password) > 72:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    session = get_session()
    try:
        user = session.query(UserRecord).filter(UserRecord.email == req.email).first()
        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        # Update last_login
        user.last_login = datetime.datetime.utcnow()
        session.commit()

        token = create_access_token(data={"sub": str(user.id), "email": user.email})
        logger.info("User logged in: %s", user.username)
        return TokenResponse(access_token=token)
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@auth_router.get("/me", response_model=UserResponse)
def get_me(current_user: UserRecord = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user
