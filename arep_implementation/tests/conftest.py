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
