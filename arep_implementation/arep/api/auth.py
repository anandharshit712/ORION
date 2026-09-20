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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import joinedload

import hashlib
import os as _os
import secrets
import datetime as _dt

from arep.api.ratelimit import limiter, login_limit, signup_limit
from arep.config import get_config
from arep.config.env import get_settings
from arep.database.connection import get_session, session_scope
from arep.database.models import UserRecord, OrganisationRecord
from arep.database.repository import OrganisationRepository, PasswordResetRepository
from arep.utils.logging_config import get_logger

logger = get_logger("api.auth")

# ── Config ───────────────────────────────────────────────────────────────

from arep.config.validate import resolve_secret_key

SECRET_KEY = resolve_secret_key()
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
        user = (
            session.query(UserRecord)
            .options(joinedload(UserRecord.organisation))
            .filter(UserRecord.id == user_id)
            .first()
        )
        if user is None:
            raise credentials_exception
        # Access the relationship now while session is open so it's
        # available after session.close() — avoids DetachedInstanceError
        _ = user.organisation
        session.expunge_all()
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


def get_scope_org_id(request: Request) -> Optional[str]:
    """
    Org-id to use when filtering org-scoped queries.

    Superadmin → None (sees all orgs). Regular user → their org_id.
    Pass the result as `org_id=` to repository list methods that already
    accept Optional[str] (None == no filter).
    """
    org_id, _, role = get_request_principal(request)
    if role == "superadmin":
        return None
    return org_id


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
    email_verified: bool
    org_id: Optional[str]
    role: str
    created_at: datetime.datetime
    last_login: Optional[datetime.datetime]
    organisation: Optional[OrgSummary] = None

    class Config:
        from_attributes = True


# ── Router ───────────────────────────────────────────────────────────────

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ── Email verification (Phase 0.4, D-04) ─────────────────────────────────

def generate_verification_token() -> tuple[str, str]:
    """Return (raw token, SHA256 hash). Only the hash is ever stored.

    Same shape as the password-reset token: 64 hex characters from
    secrets.token_hex(32). A database read must not yield anything that can be
    replayed as a link.
    """
    raw = secrets.token_hex(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _send_verification(email: str, raw_token: str) -> None:
    """Deliver the verification link, swallowing delivery failures.

    A signup that succeeded must not report failure because SMTP was briefly
    down — the user can ask for a resend. The error is logged, not raised.
    """
    from arep.api.email_sender import send_verification_email

    link = f"{get_settings().public_url}/verify-email?token={raw_token}"
    try:
        send_verification_email(email, link)
    except Exception:
        logger.error("Verification email delivery failed for %s", email)


def require_verified_email(request: Request) -> None:
    """Dependency: refuse actions that spend credits or run customer code.

    D-04's rule is that an unverified account may sign in and look around but
    may not start runs, mint API keys or upload models — the operations that
    cost money or execute submitted code. Read-only routes stay open, so the
    dashboard is not a dead end while someone finds the email.

    Superadmins bypass, consistently with require_role/require_plan.
    """
    from arep.api.middleware import SUPERADMIN_ROLE

    if getattr(request.state, "role", None) == SUPERADMIN_ROLE:
        return

    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = get_session()
    try:
        user = session.query(UserRecord).filter_by(id=int(user_id)).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if not user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Email address not verified. Check your inbox for the "
                    "verification link, or request a new one at "
                    "POST /api/auth/resend-verification."
                ),
            )
    finally:
        session.close()


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
        # Grant beta credits when billing is disabled, otherwise start on free tier.
        cfg = get_config()
        if cfg.billing.billing_enabled:
            initial_plan = "free"
            initial_credits = 50        # free tier allocation
        else:
            initial_plan = "beta"
            initial_credits = cfg.billing.beta_credits  # 1000 by default

        org = org_repo.create(
            name=org_name,
            slug=candidate,
            plan=initial_plan,
            run_credits=initial_credits,
        )

        raw_token, token_hash = generate_verification_token()
        user = UserRecord(
            org_id=org.id,
            role="owner",
            email=req.email,
            username=req.username,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
            # D-04: signup no longer auto-activates the address.
            email_verified=False,
            verification_token_hash=token_hash,
            verification_sent_at=_dt.datetime.utcnow(),
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

    # Sent after the transaction commits: an address that gets a link for an
    # account that then failed to save is worse than a missing email.
    _send_verification(req.email, raw_token)
    return user


# The `request: Request` AND `response: Response` parameters on the three routes
# below are both required by slowapi, and neither is used by the handler bodies:
#
#   request  — the limiter reads its bucket key off it.
#   response — with headers_enabled the limiter writes X-RateLimit-* into the
#              endpoint's `response` kwarg whenever the handler returns
#              something that is not a starlette Response (these return Pydantic
#              models). Without the parameter it receives None and raises, so
#              every call 500s once the limiter is enabled.
#
# Dropping either one breaks the route at call time, not at import. Limits come
# from api.rate_limit_* (D-03).

@auth_router.post("/signup", response_model=UserResponse, status_code=201)
@limiter.limit(signup_limit)
def signup(req: SignupRequest, request: Request, response: Response):
    """Create a new organisation and its first owner user."""
    return _create_user_with_org(req)


@auth_router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit(signup_limit)
def register(req: SignupRequest, request: Request, response: Response):
    """Legacy alias of /signup."""
    return _create_user_with_org(req)


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit(login_limit)
def login(req: LoginRequest, request: Request, response: Response):
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


# ── Email verification endpoints (Phase 0.4, D-04) ───────────────────────

class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str


class SimpleMessageResponse(BaseModel):
    message: str


@auth_router.post("/verify-email", response_model=SimpleMessageResponse)
def verify_email(req: VerifyEmailRequest):
    """
    Consume a verification token and mark the address verified.

    Single-use: the hash is cleared on success, so a link that leaks from a
    browser history or a forwarded email cannot be replayed. Public by design —
    the token is the credential, and requiring a session first would break the
    common case of opening the link in a different browser.
    """
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    ttl = _dt.timedelta(hours=get_settings().verification_token_ttl_hours)

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(
            verification_token_hash=token_hash
        ).first()

        # One message for "no such token" and "expired": distinguishing them
        # tells a stranger which tokens once existed.
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token.",
            )
        sent_at = user.verification_sent_at
        if sent_at is None or _dt.datetime.utcnow() - sent_at > ttl:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token.",
            )

        user.email_verified = True
        user.email_verified_at = _dt.datetime.utcnow()
        user.verification_token_hash = None
        logger.info("Email verified for user=%s", user.id)

    return SimpleMessageResponse(message="Email verified. You can now start runs.")


@auth_router.post("/resend-verification", response_model=SimpleMessageResponse)
@limiter.limit(signup_limit)
def resend_verification(
    req: ResendVerificationRequest, request: Request, response: Response,
):
    """
    Issue a fresh verification link.

    Always answers the same way, whether or not the address exists and whether
    or not it is already verified — otherwise this endpoint becomes an oracle
    for which emails hold ORION accounts. Carries the signup rate limit (per IP)
    plus a per-user hourly cap, so it cannot be used to mailbomb one address.
    """
    ok = SimpleMessageResponse(
        message="If that address needs verifying, a new link has been sent.",
    )
    settings = get_settings()

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email=req.email).first()
        if user is None or user.email_verified:
            return ok

        last_sent = user.verification_sent_at
        if last_sent is not None:
            since = _dt.datetime.utcnow() - last_sent
            min_gap = _dt.timedelta(hours=1) / max(settings.verification_resend_per_hour, 1)
            if since < min_gap:
                logger.warning("Verification resend throttled for user=%s", user.id)
                return ok

        raw_token, token_hash = generate_verification_token()
        user.verification_token_hash = token_hash
        user.verification_sent_at = _dt.datetime.utcnow()
        email = user.email

    _send_verification(email, raw_token)
    return ok


# ── Password reset schemas ────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Email address of the account to reset")


class ForgotPasswordResponse(BaseModel):
    message: str  # always the same text to avoid email enumeration


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=64, max_length=64,
                       description="64-hex reset token from the email link")
    new_password: str = Field(..., min_length=6)


# ── Password reset routes ────────────────────────────────────────────────

@auth_router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(req: ForgotPasswordRequest, request: Request):
    """
    Request a password reset link.

    Always returns the same message regardless of whether the email exists
    to prevent account enumeration. The reset link is emailed when SMTP is
    configured, or logged to the server console in dev/beta mode.
    """
    from arep.api.email_sender import send_password_reset_email

    settings = get_settings()
    ok_msg = ForgotPasswordResponse(
        message="If that email is registered, a reset link has been sent."
    )

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email=req.email).first()
        if user is None:
            return ok_msg  # silent — do not reveal whether email exists

        pr_repo = PasswordResetRepository(session)

        # Rate-limit: max N requests per hour per user
        since = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
        recent = pr_repo.count_recent_for_user(user.id, since)
        if recent >= settings.reset_rate_limit_per_hour:
            logger.warning("Reset rate limit hit for user=%s", user.id)
            return ok_msg  # silently swallow — no information leak

        # Generate single-use token: 64 hex chars, store its SHA256 hash
        raw_token = secrets.token_hex(32)               # 64 hex characters
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = (
            _dt.datetime.utcnow()
            + _dt.timedelta(minutes=settings.reset_token_ttl_minutes)
        )
        client_ip = request.client.host if request.client else None
        pr_repo.create(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip=client_ip,
        )

    reset_link = f"{settings.public_url}/reset-password?token={raw_token}"
    try:
        send_password_reset_email(req.email, reset_link)
    except Exception:
        # Email failure should not expose errors to the caller
        logger.error("Reset email delivery failed for %s", req.email)

    return ok_msg


@auth_router.post("/reset-password", response_model=ForgotPasswordResponse)
def reset_password(req: ResetPasswordRequest):
    """
    Consume a reset token and set a new password.

    The token is single-use and expires after reset_token_ttl_minutes (default 15 min).
    """
    if len(req.new_password) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot be longer than 72 characters",
        )

    token_hash = hashlib.sha256(req.token.encode()).hexdigest()

    with session_scope() as session:
        pr_repo = PasswordResetRepository(session)
        record = pr_repo.get_active_by_hash(token_hash)

        if record is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

        user = session.query(UserRecord).filter_by(id=record.user_id).first()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

        # Update password + mark token used + invalidate other tokens
        user.hashed_password = hash_password(req.new_password)
        pr_repo.mark_used(record.id)
        pr_repo.invalidate_all_for_user(user.id)
        logger.info("Password reset successful for user=%s", user.id)

    return ForgotPasswordResponse(message="Password updated successfully. You can now log in.")
