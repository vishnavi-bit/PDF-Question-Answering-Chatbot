"""Alembic migration tests: fresh databases, existing databases with data, backups and no data loss."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.database import migrations
from app.database.connection import Base
from app.database.models import Conversation, Document, Message


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _counts(path: Path) -> dict[str, int]:
    connection = sqlite3.connect(path)
    try:
        names = [row[0] for row in connection.execute("select name from sqlite_master where type='table' and name!='alembic_version'")]
        return {name: connection.execute(f'select count(*) from "{name}"').fetchone()[0] for name in names}
    finally:
        connection.close()


def _revision(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("select version_num from alembic_version")]
    finally:
        connection.close()


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    target = tmp_path / "backups"
    monkeypatch.setattr(migrations, "BACKUP_DIR", target)
    return target


def _old_style_database(path: Path) -> None:
    """A database like the one the app created before Alembic: tables plus real rows."""
    engine = create_engine(_url(path))
    # only the tables that existed before Alembic (later tables come from their own migrations)
    baseline = [t for t in Base.metadata.sorted_tables if t.name in {"documents", "document_chunks", "conversations", "messages", "study_sets", "quiz_attempts", "flashcard_studies"}]
    Base.metadata.create_all(engine, tables=baseline)
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=engine)()
    document = Document(
        id="existing-doc-1",
        filename="existing.pdf",
        original_filename="existing.pdf",
        file_path="/tmp/existing.pdf",
        file_hash="a" * 64,
        file_size=123,
        page_count=2,
        processing_status="ready",
        total_chunks=0,
    )
    conversation = Conversation(title="Existing chat")
    session.add_all([document, conversation])
    session.flush()
    session.add(Message(conversation_id=conversation.id, role="user", content="Kept question"))
    session.commit()
    session.close()
    engine.dispose()


def test_fresh_database_gets_all_tables_and_the_baseline_revision(tmp_path, backup_dir):
    path = tmp_path / "fresh.db"

    migrations.run_migrations(_url(path))

    counts = _counts(path)
    assert {"documents", "document_chunks", "conversations", "messages", "study_sets", "quiz_attempts", "flashcard_studies"} <= set(counts)
    assert _revision(path) == ["0003_document_extraction"]


def test_existing_database_keeps_every_row(tmp_path, backup_dir):
    path = tmp_path / "existing.db"
    _old_style_database(path)
    before = _counts(path)

    migrations.run_migrations(_url(path))

    after = _counts(path)
    assert {table: after[table] for table in before} == before  # every existing table keeps its rows
    connection = sqlite3.connect(path)
    assert connection.execute("select content from messages").fetchone()[0] == "Kept question"
    assert connection.execute("select filename from documents").fetchone()[0] == "existing.pdf"
    connection.close()
    assert _revision(path) == ["0003_document_extraction"]


def test_running_migrations_twice_does_nothing_the_second_time(tmp_path, backup_dir):
    path = tmp_path / "twice.db"
    _old_style_database(path)
    migrations.run_migrations(_url(path))
    after_first = _counts(path)
    backups_after_first = sorted(backup_dir.glob("*.db"))

    migrations.run_migrations(_url(path))

    assert _counts(path) == after_first
    assert sorted(backup_dir.glob("*.db")) == backups_after_first  # no new backup when nothing is pending


def test_a_backup_is_saved_before_pending_migrations_are_applied(tmp_path, backup_dir):
    path = tmp_path / "backup-me.db"
    _old_style_database(path)
    before = _counts(path)

    migrations.run_migrations(_url(path))

    backups = list(backup_dir.glob("auto-before-migration-*.db"))
    assert len(backups) == 1
    assert _counts(backups[0]) == before  # the backup holds the rows as they were before migrating


def test_downgrade_never_deletes_user_data(tmp_path, backup_dir):
    from alembic import command

    path = tmp_path / "downgrade.db"
    _old_style_database(path)
    migrations.run_migrations(_url(path))
    before = _counts(path)

    command.downgrade(migrations._alembic_config(_url(path)), "base")

    assert _counts(path) == before


def test_backup_helper_returns_none_for_missing_file(tmp_path, backup_dir):
    assert migrations.backup_sqlite_file(tmp_path / "missing.db") is None


def test_app_startup_uses_the_same_migrations(tmp_path, backup_dir, monkeypatch):
    """init_db must call the migration runner (it no longer creates tables on its own)."""
    called = []
    monkeypatch.setattr(migrations, "run_migrations", lambda url=None: called.append(url))
    from app.database import init_db as init_module

    monkeypatch.setattr(init_module, "engine", create_engine(_url(tmp_path / "startup.db")))
    init_module.init_db()
    assert called == [None]


NEW_TABLES = {
    "study_notes", "mock_exams", "mock_exam_attempts", "flashcard_reviews",
    "revision_plans", "mind_maps", "research_reports", "saved_questions",
}


def test_phase4_tables_are_created_on_fresh_databases(tmp_path, backup_dir):
    path = tmp_path / "phase4-fresh.db"
    migrations.run_migrations(_url(path))
    assert NEW_TABLES <= set(_counts(path))


def test_phase4_upgrade_keeps_existing_study_and_chat_data(tmp_path, backup_dir):
    path = tmp_path / "phase4-existing.db"
    _old_style_database(path)
    before = _counts(path)
    migrations.run_migrations(_url(path))
    after = _counts(path)
    assert {table: after[table] for table in before} == before
    assert NEW_TABLES <= set(after)


def test_phase4_downgrade_keeps_the_new_tables_and_data(tmp_path, backup_dir):
    from alembic import command

    path = tmp_path / "phase4-downgrade.db"
    _old_style_database(path)
    migrations.run_migrations(_url(path))
    before = _counts(path)
    command.downgrade(migrations._alembic_config(_url(path)), "0001_baseline")
    assert _counts(path) == before

