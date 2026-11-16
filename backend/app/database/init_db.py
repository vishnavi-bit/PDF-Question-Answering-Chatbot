"""
Database initialisation.

Creates all tables (if they do not exist yet) and marks documents that were
still "processing" when the server stopped as "failed".

Run manually with:  python -m app.database.init_db
"""

from __future__ import annotations

import logging

from sqlalchemy import update

from app.core.config import get_settings
from app.database import models  # noqa: F401  (registers the models with Base)
from app.database.connection import Base, SessionLocal, engine

logger = logging.getLogger(__name__)


def init_db() -> None:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    # Schema changes go through Alembic migrations (they never drop existing data).
    from app.database.migrations import run_migrations

    run_migrations()

    # A document stuck in "processing" means the server stopped during indexing.
    db = SessionLocal()
    try:
        result = db.execute(
            update(models.Document)
            .where(models.Document.processing_status == "processing")
            .values(
                processing_status="failed",
                error_message="Processing was interrupted. Please upload the PDF again.",
            )
        )
        db.commit()
        if result.rowcount:
            logger.warning("Marked %s interrupted document(s) as failed", result.rowcount)
    finally:
        db.close()
    logger.info("Database ready")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("Database initialised successfully.")
