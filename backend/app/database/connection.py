"""Database engine, session factory and the declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import BACKEND_DIR, get_settings

SQLITE_RELATIVE_PREFIX = "sqlite:///./"


class Base(DeclarativeBase):
    pass


def resolve_database_url(url: str) -> str:
    """
    Make relative SQLite paths (sqlite:///./data/app.db) point inside backend/
    so the app works no matter which folder it is started from.
    """
    if url.startswith(SQLITE_RELATIVE_PREFIX):
        relative = url[len(SQLITE_RELATIVE_PREFIX):]
        absolute = (BACKEND_DIR / relative).resolve()
        absolute.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute.as_posix()}"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        # absolute path given: make sure its folder exists
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    return url


def create_db_engine(url: str | None = None) -> Engine:
    resolved = resolve_database_url(url or get_settings().database_url)
    engine = create_engine(resolved, connect_args={"check_same_thread": False})

    if resolved.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # pragma: no cover - tiny hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine: Engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_file_path() -> Path | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return Path(url.database)
