"""
Shared pytest configuration.

Rate limiting (Phase 0.3, D-03) is off for the suite by default. Every test
shares one client address ("testclient"), so the 120/minute global limit starts
returning 429 partway through any module that makes a few dozen requests, and
the 3/hour signup limit breaks any module that creates more than three orgs —
failures that say nothing about the code under test.

This must run before ``arep.api.ratelimit`` is imported, because
``Limiter.enabled`` is fixed at construction from config. pytest imports
conftest before test modules, and the test modules build the app inside
fixtures, so setting it here is early enough.

``tests/test_api_hardening.py`` re-enables the limiter deliberately for the
tests that exercise it.
"""

import os

# setdefault, not assignment: CI can force it on to check the wiring end to end.
os.environ.setdefault("ORION_RATE_LIMIT_ENABLED", "false")


def verify_email_for(email: str) -> None:
    """Mark a signed-up test user's address verified (Phase 0.4, D-04).

    Signup leaves an account unverified, and an unverified account cannot start
    runs, mint API keys or upload models. Most test modules are exercising those
    features rather than the verification flow itself, so they call this right
    after signing up instead of round-tripping an emailed token.

    tests/test_email_verification.py deliberately does NOT use this — it drives
    the real link.
    """
    import datetime

    from arep.database.connection import session_scope
    from arep.database.models import UserRecord

    with session_scope() as session:
        user = session.query(UserRecord).filter_by(email=email).first()
        if user is not None:
            user.email_verified = True
            user.email_verified_at = datetime.datetime.utcnow()
