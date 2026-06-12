"""
Environment / settings loader.

Loads .env at the project root on import (idempotent — safe in tests too).
Provides a single Settings dataclass read once at startup.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Walk up from this file: arep/config/env.py → arep/config → arep → project root.
# .env lives one level above arep_implementation/ (workspace root) but may also
# live alongside arep_implementation/. Try both, parent-first.
_HERE = Path(__file__).resolve()
for candidate in (
    _HERE.parent.parent.parent.parent.parent / ".env",  # workspace root
    _HERE.parent.parent.parent.parent / ".env",         # arep_implementation/
):
    if candidate.is_file():
        load_dotenv(candidate, override=False)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from: str
    smtp_from_name: str
    smtp_use_tls: bool
    public_url: str
    reset_token_ttl_minutes: int
    reset_rate_limit_per_hour: int
    redis_url: str

    @property
    def email_enabled(self) -> bool:
        """SMTP configured? If false, sender logs to console instead."""
        return bool(self.smtp_host and self.smtp_from)


def get_settings() -> Settings:
    return Settings(
        smtp_host=os.environ.get("SMTP_HOST", "").strip(),
        smtp_port=int(os.environ.get("SMTP_PORT", "587") or "587"),
        smtp_user=os.environ.get("SMTP_USER", "").strip(),
        smtp_pass=os.environ.get("SMTP_PASS", ""),
        smtp_from=os.environ.get("SMTP_FROM", "").strip(),
        smtp_from_name=os.environ.get("SMTP_FROM_NAME", "ORION").strip(),
        smtp_use_tls=_bool("SMTP_USE_TLS", True),
        public_url=os.environ.get("ORION_PUBLIC_URL", "http://localhost:5173").rstrip("/"),
        reset_token_ttl_minutes=int(os.environ.get("RESET_TOKEN_TTL_MINUTES", "15") or "15"),
        reset_rate_limit_per_hour=int(os.environ.get("RESET_RATE_LIMIT_PER_HOUR", "5") or "5"),
        redis_url=os.environ.get("ORION_REDIS_URL", "redis://localhost:6379/0"),
    )
