"""
The Alembic chain, checked without a database (D-13).

Dev builds its schema with ``create_all`` from the ORM, so the migrations are
only ever executed by the Postgres CI job. When that job is red for an unrelated
reason, a broken migration can sit on main indefinitely — and it did: 013 created
a ``webhook_deliveries`` table that 002 already creates, so ``alembic upgrade
head`` failed on every fresh database, while every local test passed.

Alembic can render the whole chain as SQL without connecting to anything
(``--sql``, "offline mode"). That is enough to catch the two mistakes that are
invisible on SQLite and fatal on Postgres:

  - a table created while one of the same name already exists;
  - a boolean column defaulted with ``sa.text("1")``, which renders as
    ``BOOLEAN DEFAULT 1`` and which Postgres refuses as an integer default on a
    boolean column.

These are string checks on generated SQL, not a substitute for running the
migrations. The Postgres job still does that. This only makes the common failures
fail here, in two seconds, instead of in CI twenty minutes later.
"""

from __future__ import annotations

import io
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

alembic_command = pytest.importorskip("alembic.command")
from alembic.config import Config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INI = ROOT / "alembic.ini"

# Offline rendering never opens a socket, so the host and database here are
# never contacted. The dialect is the only part that matters: it decides how
# every default and type is rendered.
OFFLINE_URL = "postgresql://offline:offline@localhost:1/offline"


def _render(direction: str) -> str:
    """Return the SQL Alembic would run, without running any of it."""
    config = Config(str(INI))
    config.set_main_option("sqlalchemy.url", OFFLINE_URL)
    config.set_main_option("script_location", str(ROOT / "arep/database/migrations"))

    buffer = io.StringIO()
    previous = os.environ.get("ORION_DATABASE_URL")
    os.environ["ORION_DATABASE_URL"] = OFFLINE_URL
    try:
        with redirect_stdout(buffer):
            if direction == "up":
                alembic_command.upgrade(config, "head", sql=True)
            else:
                alembic_command.downgrade(config, "head:base", sql=True)
    finally:
        if previous is None:
            os.environ.pop("ORION_DATABASE_URL", None)
        else:
            os.environ["ORION_DATABASE_URL"] = previous

    return buffer.getvalue()


# Alembic's own bookkeeping table. It is created and dropped by the runner
# rather than by any migration, and whether its DROP shows up in rendered SQL
# depends on the Alembic version - 1.18 emits it, 1.20 does not. Either way it
# is not part of the schema under test.
BOOKKEEPING = {"alembic_version"}


def _table_events(sql: str) -> list[tuple[str, str]]:
    """(action, table) pairs in the order the chain performs them."""
    pattern = re.compile(
        r"\b(CREATE TABLE|DROP TABLE)\s+(?:IF (?:NOT )?EXISTS\s+)?([A-Za-z_][\w.]*)",
        re.IGNORECASE,
    )
    return [
        (m.group(1).upper(), m.group(2).lower())
        for m in pattern.finditer(sql)
        if m.group(2).lower() not in BOOKKEEPING
    ]


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    return _render("up")


@pytest.fixture(scope="module")
def downgrade_sql() -> str:
    return _render("down")


def test_no_table_is_created_while_one_of_that_name_exists(upgrade_sql):
    """The 013 defect. Two migrations both owned the name `webhook_deliveries`,
    so the chain could not be applied to a fresh database at all."""
    live: set[str] = set()

    for action, table in _table_events(upgrade_sql):
        if action == "CREATE TABLE":
            assert table not in live, (
                f"{table!r} is created while a table of that name already exists — "
                f"`alembic upgrade head` will fail on any fresh database"
            )
            live.add(table)
        else:
            live.discard(table)


def test_no_boolean_column_is_defaulted_with_an_integer(upgrade_sql):
    """`server_default=sa.text("1")` renders as `BOOLEAN DEFAULT 1`. SQLite
    takes it; Postgres rejects it as an integer default on a boolean column, so
    the mistake is invisible everywhere developers actually run."""
    offenders = re.findall(
        r"^\s*(\w+)\s+BOOLEAN\s+DEFAULT\s+([01])\b",
        upgrade_sql,
        re.IGNORECASE | re.MULTILINE,
    )
    assert not offenders, (
        "boolean columns defaulted with an integer (use sa.true()/sa.false()): "
        + ", ".join(f"{col} DEFAULT {val}" for col, val in offenders)
    )


def test_the_downgrade_leaves_no_table_behind(downgrade_sql, upgrade_sql):
    """Downgrading to base has to undo everything. A table left standing means
    a later re-upgrade hits the create-while-exists failure above."""
    live: set[str] = set()
    for action, table in _table_events(upgrade_sql):
        live.add(table) if action == "CREATE TABLE" else live.discard(table)

    for action, table in _table_events(downgrade_sql):
        live.discard(table) if action == "DROP TABLE" else live.add(table)

    assert not live, f"downgrade to base leaves these tables behind: {sorted(live)}"


def test_a_table_a_migration_recreates_on_downgrade_is_dropped_again_later(
    downgrade_sql,
):
    """013 drops 002's dead `webhook_deliveries` and recreates it on the way
    down, because downgrading to 012 must leave the schema upgrading to 012
    produces. That only holds if 002's own downgrade then drops it — otherwise
    one bad migration becomes a chain nobody can reverse."""
    events = _table_events(downgrade_sql)
    deliveries = [a for a, t in events if t == "webhook_deliveries"]

    assert deliveries, "the downgrade path never mentions webhook_deliveries"
    assert deliveries[-1] == "DROP TABLE", (
        "the last thing the downgrade does to webhook_deliveries is "
        f"{deliveries[-1]}, so downgrading to base leaves it behind"
    )


# -- Which driver a Postgres URL means --------------------------------------


def test_a_bare_postgres_url_names_the_driver_we_ship():
    """SQLAlchemy resolves the DBAPI from the URL scheme, and in 2.1 it changed
    what a bare `postgresql://` means: psycopg2 before, psycopg v3 after.

    This project ships `psycopg2-binary`, so the first environment to resolve
    SQLAlchemy 2.1 died on `No module named 'psycopg'` — CI, and any fresh
    production deploy next, on a morning nobody changed a line. Naming the
    driver makes it a decision instead of a default that can move again.
    """
    from arep.config.validate import pin_postgres_driver

    assert (
        pin_postgres_driver("postgresql://u:p@host:5432/db")
        == "postgresql+psycopg2://u:p@host:5432/db"
    )


def test_the_heroku_style_alias_is_normalised_too():
    """`postgres://` is what several hosts still hand out, and SQLAlchemy
    dropped it entirely."""
    from arep.config.validate import pin_postgres_driver

    assert pin_postgres_driver("postgres://u@h/db") == "postgresql+psycopg2://u@h/db"


def test_an_explicitly_chosen_driver_is_left_alone():
    """Someone who wrote `+psycopg` or `+asyncpg` meant it. Overriding an
    explicit choice with ours would be the same class of surprise."""
    from arep.config.validate import pin_postgres_driver

    for url in (
        "postgresql+psycopg://u@h/db",
        "postgresql+asyncpg://u@h/db",
        "postgresql+psycopg2://u@h/db",
    ):
        assert pin_postgres_driver(url) == url


def test_non_postgres_urls_are_untouched():
    from arep.config.validate import pin_postgres_driver

    for url in ("sqlite:///arep.db", "sqlite+aiosqlite:///x.db", "mysql://u@h/db"):
        assert pin_postgres_driver(url) == url


def test_alembic_resolves_the_same_driver_as_the_application():
    """The migration runner read ORION_DATABASE_URL directly, so it could pick
    a different DBAPI than the app — which is exactly what happened."""
    env = (ROOT / "arep/database/migrations/env.py").read_text(encoding="utf-8")
    assert "pin_postgres_driver" in env, (
        "alembic env.py bypasses the URL resolver, so migrations and the "
        "application can disagree about which driver to load"
    )


def test_rendering_the_chain_does_not_switch_off_everyone_elses_logging():
    """Alembic's env.py calls `fileConfig`, which disables every existing
    logger unless told not to.

    That is a side effect on whatever process ran the migration. Under pytest
    it meant every test *after* this file quietly stopped capturing log output,
    so assertions about warnings failed somewhere else entirely — three of them
    did, and they pointed at the wrong code. In production it would mute the
    application's own logging for anything that migrates in process.
    """
    import logging

    canary = logging.getLogger("arep.tests.logging_canary")
    assert not canary.disabled

    _render("up")

    assert not canary.disabled, (
        "rendering the migration chain disabled a pre-existing logger — "
        "env.py needs fileConfig(..., disable_existing_loggers=False)"
    )
