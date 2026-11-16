"""Study and research upgrade: notes, mock exams, spaced repetition, revision, mind maps, research, saved questions.

Additive only: creates new tables and never changes or drops existing ones.
Columns are written out here (not taken from the current models), so this revision keeps
doing exactly the same thing even if the models change later.

downgrade() does nothing, so rolling back can never delete student data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_study_upgrade"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> sa.sql.elements.TextClause:
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "study_notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("length", sa.String(8), nullable=False),
        sa.Column("document_ids_json", sa.Text(), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(), server_default=_now()),
    )
    op.create_table(
        "mock_exams",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("document_ids_json", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
    )
    op.create_table(
        "mock_exam_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("auto_submitted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("late", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("total_mcq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percent", sa.Float(), nullable=True),
        sa.Column("answers_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
        sa.ForeignKeyConstraint(["exam_id"], ["mock_exams.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_mock_exam_attempts_exam_id", "mock_exam_attempts", ["exam_id"])

    op.create_table(
        "flashcard_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.Column("card_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["deck_id"], ["study_sets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("deck_id", "card_index", name="uq_flashcard_review_card"),
    )
    op.create_index("ix_flashcard_reviews_deck_id", "flashcard_reviews", ["deck_id"])
    op.create_index("ix_flashcard_reviews_due_date", "flashcard_reviews", ["due_date"])

    op.create_table(
        "revision_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deck_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("day_offset", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
        sa.ForeignKeyConstraint(["deck_id"], ["study_sets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revision_plans_deck_id", "revision_plans", ["deck_id"])
    op.create_index("ix_revision_plans_due_date", "revision_plans", ["due_date"])

    op.create_table(
        "mind_maps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_ids_json", sa.Text(), nullable=False),
        sa.Column("tree_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(), server_default=_now()),
    )
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_ids_json", sa.Text(), nullable=False),
        sa.Column("body_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
        sa.Column("updated_at", sa.DateTime(), server_default=_now()),
    )
    op.create_table(
        "saved_questions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), server_default=_now()),
    )


def downgrade() -> None:
    # Never drop student data automatically: a rollback leaves the tables in place.
    pass
