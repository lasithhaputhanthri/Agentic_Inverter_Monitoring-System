"""Database connection, engine, and session management.

Purpose: Manages SQLAlchemy database engine, session makers, and table creation.
Inputs: Database URL string or settings.
Outputs: SQLAlchemy Engine and Session factories.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.storage.models import Base

DEFAULT_DB_PATH = Path("data/iir.db")
DEFAULT_DB_URL = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


def get_engine(db_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine with standard timeouts and connection configurations."""
    url: str = db_url if db_url else (os.getenv("DATABASE_URL") or DEFAULT_DB_URL)
    if url.startswith("sqlite") and not url.endswith(":memory:"):
        # Ensure parent directory exists for file-based SQLite
        db_file = url.replace("sqlite:///", "")
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a thread-safe Session factory bound to the engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(engine: Engine) -> None:
    """Create all declarative tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def get_db_session(engine: Engine) -> Generator[Session, None, None]:
    """Dependency helper providing a scoped database session."""
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
