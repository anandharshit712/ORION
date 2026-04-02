"""
ORION Database Connection.

Manages SQLAlchemy engine and session factory.
Supports SQLite (default) and PostgreSQL.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from arep.database.models import Base
from arep.utils.logging_config import get_logger

logger = get_logger("database.connection")

# Module-level singleton
_engine = None
_SessionFactory = None


def init_database(
    url: Optional[str] = None,
    echo: bool = False,
) -> None:
    """
    Initialize the database engine and create tables.

    Args:
        url: SQLAlchemy connection URL.
             Defaults to SQLite file in project root.
        echo: If True, log all SQL statements.
    """
    global _engine, _SessionFactory

    if url is None:
        url = os.environ.get(
            "ORION_DATABASE_URL",
            "postgresql://Harshit:Harshit@localhost:5432/orion",
        )

    logger.info("Initializing database: %s", url.split("@")[-1])  # hide credentials

    engine_kwargs = {"echo": echo}
    if url.startswith("postgresql"):
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_size"] = 5

    _engine = create_engine(url, **engine_kwargs)
    _SessionFactory = sessionmaker(bind=_engine)

    # Create all tables
    Base.metadata.create_all(_engine)
    logger.info("Database tables created/verified")


def get_session() -> Session:
    """
    Get a new database session.

    Raises:
        RuntimeError: If init_database() hasn't been called.
    """
    if _SessionFactory is None:
        init_database()  # auto-init with defaults
    return _SessionFactory()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with auto-commit/rollback.

    Usage:
        with session_scope() as session:
            session.add(record)
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    """Get the current engine (for advanced use)."""
    if _engine is None:
        init_database()
    return _engine


def reset_database() -> None:
    """Drop and recreate all tables. USE WITH CAUTION."""
    global _engine
    if _engine is None:
        init_database()
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)
    logger.warning("Database reset complete — all data dropped")
