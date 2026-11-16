"""Document endpoints: listing, details, PDF file serving, deletion, path safety and health."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security import ensure_inside, sanitize_filename
from tests.helpers import make_scanned_pdf, upload_pdf


def test_list_and_get_document(client):
    document = upload_pdf(client, ["Some readable text for listing."], name="list.pdf").json()["document"]

    listing = client.get("/api/documents").json()
    assert listing["total"] == 1
    assert listing["documents"][0]["id"] == document["id"]

    details = client.get(f"/api/documents/{document['id']}").json()
    assert details["filename"] == "list.pdf"


def test_unknown_document_returns_404(client):
    assert client.get("/api/documents/unknown").status_code == 404
    assert client.delete("/api/documents/unknown").status_code == 404


def test_pdf_file_is_served_for_ready_documents(client):
    document = upload_pdf(client, ["Viewable page text that is long enough to be indexed as readable content."]).json()["document"]

    response = client.get(f"/api/documents/{document['id']}/file")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_file_is_not_served_for_documents_that_failed(client):
    document = upload_pdf(client, name="scan.pdf", data=make_scanned_pdf()).json()["document"]
    response = client.get(f"/api/documents/{document['id']}/file")
    assert response.status_code == 404


def test_delete_removes_stored_file_and_record(client):
    from app.database.connection import SessionLocal
    from app.database.models import Document

    document = upload_pdf(client, ["Delete me completely. This sentence makes the document long enough to be indexed."]).json()["document"]

    session = SessionLocal()
    try:
        file_on_disk = Path(session.get(Document, document["id"]).file_path)
    finally:
        session.close()
    assert file_on_disk.exists()

    assert client.delete(f"/api/documents/{document['id']}").status_code == 204

    assert not file_on_disk.exists()
    assert client.get(f"/api/documents/{document['id']}").status_code == 404


def test_path_traversal_outside_storage_is_blocked(tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()
    with pytest.raises(ValueError):
        ensure_inside(base, base / ".." / "secret.txt")


def test_sanitize_filename_removes_folders_and_odd_characters():
    assert sanitize_filename("..\\..\\evil<script>.pdf") == "evil_script_.pdf"
    assert sanitize_filename("") == "document.pdf"
    assert sanitize_filename("report") == "report.pdf"


def test_health_reports_missing_api_key_without_exposing_it(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["gemini_api_key_configured"] is False
    assert "api_key" not in str(body).lower().replace("gemini_api_key_configured", "")


def test_api_docs_are_available(client):
    assert client.get("/openapi.json").status_code == 200
