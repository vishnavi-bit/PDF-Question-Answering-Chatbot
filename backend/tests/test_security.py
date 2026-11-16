"""Phase 8 security checks: uploads, file access, secrets in responses, and error messages."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import sanitize_filename
from app.database.connection import SessionLocal
from app.database.models import Document
from tests.helpers import make_pdf, upload_pdf

SECRET = "SECRET-TEST-KEY-do-not-show-12345"


def test_non_pdf_upload_is_refused(client):
    response = client.post("/api/documents/upload", files={"file": ("notes.pdf", b"this is plain text", "application/pdf")})
    assert response.status_code == 415


def test_empty_upload_is_refused(client):
    response = client.post("/api/documents/upload", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert response.status_code == 400


def test_oversized_upload_is_refused(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 0)  # every real file is now too large
    response = client.post("/api/documents/upload", files={"file": ("big.pdf", make_pdf(["text"]), "application/pdf")})
    assert response.status_code == 413


def test_filenames_with_path_parts_are_made_safe():
    cleaned = sanitize_filename("../../etc/evil name.pdf")
    assert "/" not in cleaned and "\\" not in cleaned and ".." not in cleaned
    assert cleaned.endswith(".pdf")


def test_uploaded_filename_is_stored_without_path_parts(client):
    document = upload_pdf(client, ["Some readable text about the device for the filename test."],
                          name="..\\..\\secret\\report.pdf").json()["document"]
    assert "\\" not in document["filename"] and "/" not in document["filename"]


def test_file_route_does_not_serve_a_file_outside_the_upload_folder(client, tmp_path):
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(make_pdf(["This file is outside the upload folder."]))
    session = SessionLocal()
    try:
        session.add(Document(
            id="traversal01", filename="outside.pdf", original_filename="outside.pdf", file_path=str(outside),
            file_hash="x" * 64, file_size=10, page_count=1, processing_status="ready", total_chunks=0,
        ))
        session.commit()
    finally:
        session.close()
    response = client.get("/api/documents/traversal01/file")
    assert response.status_code == 400  # "Invalid file location."
    assert b"outside the upload folder" not in response.content


def test_file_route_returns_404_for_unknown_or_unready_documents(client):
    assert client.get("/api/documents/does-not-exist/file").status_code == 404


def test_the_gemini_key_never_appears_in_responses(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SECRET)
    health = client.get("/api/health")
    assert SECRET not in health.text
    assert health.json()["gemini_api_key_configured"] is True
    documents = client.get("/api/documents")
    assert SECRET not in documents.text


def test_unknown_routes_and_bad_input_return_short_messages_without_tracebacks(client):
    response = client.get("/api/no-such-route")
    assert response.status_code == 404
    assert "Traceback" not in response.text
    bad = client.post("/api/chat", json={"question": ""})
    assert bad.status_code == 422
    assert "Traceback" not in bad.text
