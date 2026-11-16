"""Baseline: the schema as it was before Alembic was introduced.

Safe for existing databases: `create_all(checkfirst=True)` creates ONLY tables that
do not exist yet. Existing tables, columns and rows are never dropped, altered or
recreated. On an existing database this migration only records the version.

Future migrations (for example the SM-2 flashcard columns) are separate revisions.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.database import models  # noqa: F401  (registers every table on Base.metadata)
from app.database.connection import Base

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The schema as it was BEFORE Phase 4. Later tables are added by their own migrations.
BASELINE_TABLES = [
    "documents",
    "document_chunks",
    "conversations",
    "messages",
    "study_sets",
    "quiz_attempts",
    "flashcard_studies",
]


def upgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name in BASELINE_TABLES]
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True, tables=tables)


def downgrade() -> None:
    # Never drop user data automatically.
    pass
