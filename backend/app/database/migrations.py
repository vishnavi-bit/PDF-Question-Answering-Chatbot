"""
Database migrations (Alembic).

- Runs `alembic upgrade head` when the app starts.
- Before applying NEW migrations to a SQLite file, it saves a copy of the database in
  data/backups/ (SQLite's backup API, so it is safe while the app is running).
- Existing data is never dropped. See alembic/versions/0001_baseline.py.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from app.core.config import BACKEND_DIR
from app.database.connection import engine as default_engine

logger = logging.getLogger(__name__)
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BACKUP_DIR = BACKEND_DIR / "data" / "backups"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # % must be escaped for configparser
    return config


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite:///") or url.startswith("sqlite:///:memory:"):
        return None
    return Path(url[len("sqlite:///"):])


def _pending_revisions(url: str) -> bool:
    """True when the database is not yet at the newest migration."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        head = ScriptDirectory.from_config(_alembic_config(url)).get_current_head()
        return current != head
    finally:
        engine.dispose()


def backup_sqlite_file(path: Path) -> Path | None:
    """Copy a SQLite database into data/backups/ using the online backup API (safe while in use)."""
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / f"auto-before-migration-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    logger.info("Saved a database backup before migrating: %s", target.name)
    return target


def run_migrations(url: str | None = None) -> None:
    """Bring the database up to the newest revision. Idempotent: a second run does nothing."""
    target_url = url or default_engine.url.render_as_string(hide_password=False)
    sqlite_file = _sqlite_path(target_url)
    if sqlite_file is not None and _pending_revisions(target_url):
        backup_sqlite_file(sqlite_file)
    command.upgrade(_alembic_config(target_url), "head")
    logger.info("Database schema is up to date")
