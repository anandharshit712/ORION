"""
A test run must never deliver mail to a real inbox.

`arep/config/env.py` auto-loads a `.env` from the workspace root, so a
developer's real SMTP credentials reach any process that imports the config —
including pytest. The suite signs up through the real `/api/auth/signup`
endpoint in twenty-one modules and resends verification in six more places, so
a full run delivered roughly thirty verification emails to a live inbox, and
several runs in one day delivered over fifty. Nothing in the test code asked
for it and nothing in it could see it happening.

Two layers stop it, and these tests pin both. Either alone would have been
enough, which is the point: the one that fails is usually the one nobody
checked.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arep.api import email_sender  # noqa: E402


def test_conftest_clears_smtp_credentials():
    """Layer one. If a .env sets these, conftest removes them before anything
    reads the config."""
    for var in ("SMTP_HOST", "SMTP_FROM", "SMTP_USER", "SMTP_PASS"):
        assert not os.environ.get(
            var
        ), f"{var} is set during the test run; a signup would deliver real mail"


def test_the_sender_refuses_under_pytest_even_when_smtp_is_configured(monkeypatch):
    """Layer two, and the one that matters.

    A test module that builds the app without conftest, or a future fixture
    that restores the variables, would defeat layer one. `PYTEST_CURRENT_TEST`
    is set by pytest for the duration of every test, so this needs no
    cooperation from the test author.
    """
    sent = []

    class _Boom:
        def __init__(self, *a, **k):
            sent.append(a)
            raise AssertionError("a test opened an SMTP connection")

    # Fully configured, as a developer's .env would leave it.
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    monkeypatch.setattr("smtplib.SMTP", _Boom)
    monkeypatch.setattr("smtplib.SMTP_SSL", _Boom)

    assert os.environ.get("PYTEST_CURRENT_TEST"), "pytest should set this"

    email_sender.send_verification_email("someone@example.com", "https://x/verify?t=1")
    email_sender.send_password_reset_email("someone@example.com", "https://x/reset?t=1")

    assert not sent, "the sender opened an SMTP connection during a test"


def test_signing_up_through_the_api_sends_nothing(monkeypatch, tmp_path):
    """End to end, the way the suite actually triggers it.

    Every module that needs an account calls this endpoint. That is the path
    that sent the mail, so that is the path worth pinning.
    """
    opened = []

    class _Boom:
        def __init__(self, *a, **k):
            opened.append(a)
            raise AssertionError("signup opened an SMTP connection")

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    monkeypatch.setattr("smtplib.SMTP", _Boom)
    monkeypatch.setattr("smtplib.SMTP_SSL", _Boom)

    db_path = tmp_path / "mail.db"
    monkeypatch.setenv("ORION_DATABASE_URL", f"sqlite:///{db_path}")

    from arep.database import connection as conn_mod

    conn_mod._engine = None
    conn_mod._SessionFactory = None
    conn_mod.init_database(url=f"sqlite:///{db_path}")

    from fastapi.testclient import TestClient

    from arep.api.app import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "mailcheck@example.com",
                "username": "mailcheck",
                "password": "password123",
                "org_name": "mail org",
                "org_slug": "mailorg",
            },
        )

    # The signup itself must still work — the guard suppresses delivery, not
    # the account.
    assert response.status_code in (200, 201), response.text
    assert not opened, "signup delivered a real verification email"

    conn_mod._engine = None
    conn_mod._SessionFactory = None
