"""Upload API tests: valid PDFs, invalid files, duplicates and scanned PDFs."""

from __future__ import annotations

from app.core.config import get_settings
from tests.helpers import make_pdf, make_scanned_pdf, upload_pdf


def test_valid_pdf_is_indexed_and_reported_ready(client):
    response = upload_pdf(client, ["The warranty lasts two years from the purchase date."], name="manual.pdf")

    assert response.status_code == 201
    body = response.json()
    document = body["document"]
    assert document["processing_status"] == "ready"
    assert document["filename"] == "manual.pdf"
    assert document["page_count"] == 1
    assert document["total_chunks"] >= 1
    assert body["duplicate"] is False


def test_non_pdf_extension_is_rejected(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 415
    assert "Only PDF" in response.json()["detail"]


def test_file_named_pdf_but_not_a_pdf_is_rejected(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("fake.pdf", b"this is just text, not a PDF", "application/pdf")},
    )
    assert response.status_code == 415


def test_empty_file_is_rejected(client):
    response = client.post("/api/documents/upload", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert response.status_code == 400


def test_file_larger_than_the_limit_is_rejected(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)  # any real file is too large now
    response = upload_pdf(client, ["Some text"])
    assert response.status_code == 413


def test_same_file_uploaded_twice_is_not_processed_again(client):
    data = make_pdf(["Identical content for the duplicate check."])
    first = upload_pdf(client, name="a.pdf", data=data).json()
    second = upload_pdf(client, name="copy.pdf", data=data).json()

    assert second["duplicate"] is True
    assert second["document"]["id"] == first["document"]["id"]

    listing = client.get("/api/documents").json()
    assert listing["total"] == 1


def test_scanned_pdf_is_saved_with_needs_ocr_status(client):
    response = upload_pdf(client, name="scan.pdf", data=make_scanned_pdf())

    assert response.status_code == 201
    document = response.json()["document"]
    assert document["processing_status"] == "needs_ocr"
    assert "OCR" in document["error_message"]
    assert document["total_chunks"] == 0


def test_unsafe_file_names_are_cleaned(client):
    response = upload_pdf(client, name="../../etc/evil name.pdf")
    filename = response.json()["document"]["filename"]

    assert "/" not in filename and "\\" not in filename and ".." not in filename
    assert filename.endswith(".pdf")


def test_stored_file_name_is_a_random_id_not_the_original_name(client):
    response = upload_pdf(client, name="my secret plan.pdf")
    document = response.json()["document"]

    stored = list(get_settings().upload_dir.glob("*.pdf"))
    assert len(stored) == 1
    assert stored[0].stem == document["id"]
