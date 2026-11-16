"""Document extraction details (Phase 7): counts of indexed tables and of pages without text.

Additive only: adds two columns to `documents` with a default of 0, so existing documents keep
all their data. downgrade() does nothing, so rolling back can never delete data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_document_extraction"
down_revision: str | None = "0002_study_upgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_COLUMNS = ("table_count", "pages_without_text")


def upgrade() -> None:
    # The 0001 baseline builds missing tables from the current models, so on a fresh database these
    # columns may already exist. Add only the columns that are missing.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("documents")}
    for name in NEW_COLUMNS:
        if name not in existing:
            op.add_column("documents", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # Intentionally empty: rolling back must never delete data.
    pass
