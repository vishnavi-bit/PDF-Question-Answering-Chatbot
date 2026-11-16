"""
Shared test setup (fixtures).

- Storage (SQLite, ChromaDB, uploads) goes to a temporary folder, never to the real storage/.
- The sentence-transformers model is replaced by a small fake embedder, so tests
  need no internet access and no model download.
- Gemini API calls are replaced by a fake function, so tests need no API key.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# ---- environment must be set BEFORE the app modules are imported ----------
TEST_ROOT = Path(tempfile.mkdtemp(prefix="pdfbot-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["CHROMA_PERSIST_DIRECTORY"] = str(TEST_ROOT / "chroma")
os.environ["UPLOAD_DIRECTORY"] = str(TEST_ROOT / "uploads")
os.environ["STATIC_DIRECTORY"] = str(TEST_ROOT / "no-frontend-build")
os.environ["GEMINI_API_KEY"] = ""  # tests must never use a real key
# The fake embedder gives lower scores than the real model, so tests use a lower threshold.
os.environ["MIN_SIMILARITY"] = "0.15"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.connection import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import embedding_service, llm_service, vector_store_service  # noqa: E402
from tests.helpers import FakeLLM, fake_embed_texts  # noqa: E402

# The real embedding function, saved before the fake is installed (used by the optional model test).
REAL_EMBED_TEXTS = embedding_service.embed_texts


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(embedding_service, "embed_texts", fake_embed_texts)
    yield


@pytest.fixture(autouse=True)
def reset_reliability_state():
    """Each test starts with no cached answers, no cooldown and no remembered requests."""
    from app.services import request_guard

    llm_service.clear_cache()
    request_guard.chat_guard.clear()
    request_guard.study_guard.clear()
    yield
    llm_service.clear_cache()


@pytest.fixture(autouse=True)
def no_real_waiting(monkeypatch):
    """Retry waits are skipped in tests so they run instantly."""
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: None)
    yield


@pytest.fixture
def llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm_service, "complete", fake)
    return fake


def _wipe_state() -> None:
    """Empty the database, the vector collection and the upload folder before each test."""
    from alembic import command

    from app.database import migrations

    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        # legacy table from the removed Research Assistant (no model any more, still created by migration 0002)
        connection.exec_driver_sql("DROP TABLE IF EXISTS research_reports")
    # build the test schema with the real migrations (no backups are written during tests)
    command.upgrade(migrations._alembic_config(str(engine.url)), "head")
    collection = vector_store_service._get_collection()
    existing = collection.get()["ids"]
    if existing:
        collection.delete(ids=existing)
    upload_dir = Path(os.environ["UPLOAD_DIRECTORY"])
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def clean_state():
    _wipe_state()
    yield


@pytest.fixture
def client():
    # raise_server_exceptions=False lets us test the 500 error responses
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
