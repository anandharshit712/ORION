"""
Startup configuration validator (Phase 0.1, D-02).

Fail-fast on missing or insecure secrets *before* the app serves traffic.
Single source of truth for resolving the JWT secret and the database URL.

Behaviour by environment (``ORION_ENV``):
  - dev/test/local: missing secret → ephemeral random secret (logged warning);
    missing DB URL → SQLite file. The app always boots.
  - anything else (prod, staging, ...): missing/weak/placeholder secret → refuse
    to boot; SQLite DB URL → refuse to boot (FOR UPDATE is a no-op on SQLite).

Called from the FastAPI lifespan (``api/app.py``) and reused by ``api/auth.py``
and ``database/connection.py`` so all three agree on the same resolution rules.
"""
from __future__ import annotations

import os
import secrets
from typing import Optional

from arep.utils.exceptions import ConfigurationError
from arep.utils.logging_config import get_logger

logger = get_logger("config.validate")

_DEV_ENVS = {"dev", "development", "test", "testing", "local"}
_MIN_SECRET_LEN = 32

# Cached ephemeral dev secret so repeated calls in one process agree.
_ephemeral_secret: Optional[str] = None


def _is_placeholder(secret: str) -> bool:
    """True for obvious shipped-default / example placeholder secrets."""
    low = secret.lower()
    # e.g. "...change...in...production", "replace_with_...", "changeme"
    return (
        ("change" in low and "produc" in low)
        or "replace" in low
        or "changeme" in low
        or "placeholder" in low
    )


def get_env() -> str:
    """Normalised deployment environment from ORION_ENV (default: dev)."""
    return os.environ.get("ORION_ENV", "dev").strip().lower()


def is_dev() -> bool:
    """True for dev/test/local environments where insecure defaults are tolerated."""
    return get_env() in _DEV_ENVS


def resolve_secret_key() -> str:
    """
    Return the JWT signing secret.

    Prod: ``ORION_SECRET_KEY`` must be set, >= 32 chars, and not a known
    placeholder — otherwise raise and refuse to boot.
    Dev: if unset/weak, generate a process-stable ephemeral secret (tokens do
    not survive a restart, which is acceptable in dev).
    """
    global _ephemeral_secret
    raw = os.environ.get("ORION_SECRET_KEY", "").strip()
    placeholder = bool(raw) and _is_placeholder(raw)
    weak = (not raw) or placeholder or (len(raw) < _MIN_SECRET_LEN)

    if not weak:
        return raw

    if not is_dev():
        if not raw:
            raise ConfigurationError(
                "ORION_SECRET_KEY is required in a non-dev environment "
                f"(ORION_ENV={get_env()!r}). Refusing to boot."
            )
        if placeholder:
            raise ConfigurationError(
                "ORION_SECRET_KEY is a placeholder value. "
                "Set a real random secret. Refusing to boot."
            )
        raise ConfigurationError(
            f"ORION_SECRET_KEY must be at least {_MIN_SECRET_LEN} characters "
            f"(got {len(raw)}). Refusing to boot."
        )

    # Dev: ephemeral secret, generated once per process.
    if _ephemeral_secret is None:
        _ephemeral_secret = secrets.token_urlsafe(48)
        logger.warning(
            "ORION_SECRET_KEY unset/weak in dev (ORION_ENV=%s) — using an "
            "ephemeral secret. Tokens will not survive a restart.",
            get_env(),
        )
    return _ephemeral_secret


def resolve_database_url() -> str:
    """
    Return the SQLAlchemy database URL.

    Prod: ``ORION_DATABASE_URL`` must be set and must not be SQLite.
    Dev: default to a local SQLite file when unset.
    """
    url = os.environ.get("ORION_DATABASE_URL", "").strip()

    if url:
        if not is_dev() and url.startswith("sqlite"):
            raise ConfigurationError(
                "SQLite is not permitted in a non-dev environment "
                f"(ORION_ENV={get_env()!r}); FOR UPDATE row locks are a no-op "
                "on SQLite. Set a PostgreSQL ORION_DATABASE_URL. Refusing to boot."
            )
        return url

    if not is_dev():
        raise ConfigurationError(
            "ORION_DATABASE_URL is required in a non-dev environment "
            f"(ORION_ENV={get_env()!r}). Refusing to boot."
        )

    logger.warning("ORION_DATABASE_URL unset in dev — defaulting to sqlite:///arep.db")
    return "sqlite:///arep.db"


def validate_startup() -> None:
    """
    Run all fail-fast checks. Call from the API lifespan and worker bootstrap.

    Raises ConfigurationError if the environment is unsafe to serve from.
    """
    resolve_secret_key()
    resolve_database_url()
    logger.info("Configuration validated (ORION_ENV=%s)", get_env())
