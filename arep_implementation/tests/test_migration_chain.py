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


def _table_events(sql: str) -> list[tuple[str, str]]:
    """(action, table) pairs in the order the chain performs them."""
    pattern = re.compile(
        r"\b(CREATE TABLE|DROP TABLE)\s+(?:IF (?:NOT )?EXISTS\s+)?([A-Za-z_][\w.]*)",
        re.IGNORECASE,
    )
    return [(m.group(1).upper(), m.group(2).lower()) for m in pattern.finditer(sql)]


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
