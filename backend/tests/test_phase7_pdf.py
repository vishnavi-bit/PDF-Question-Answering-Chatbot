"""Phase 7 tests: tables, OCR detection, large PDFs, empty pages and extraction errors."""

from __future__ import annotations

import io
import sqlite3

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

from app.core.config import get_settings
from app.database import migrations
from app.database.connection import SessionLocal
from app.database.models import DocumentChunk
from app.services import embedding_service, ocr_service, pdf_service, rag_service
from tests.helpers import make_pdf, upload_pdf

SPEC_ROWS = [["Model", "Power", "Warranty"], ["XR-500", "750 W", "2 years"], ["XR-700", "1100 W", "3 years"]]


def table_pdf(rows=SPEC_ROWS) -> bytes:
    """Page 1: an introduction. Page 2: a ruled table."""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    table = Table(rows)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    document = SimpleDocTemplate(buffer, pagesize=A4)
    document.build([Paragraph("Specifications for the range of devices.", styles["BodyText"]), PageBreak(), table])
    return buffer.getvalue()


def _chunks(document_id: str) -> list[DocumentChunk]:
    session = SessionLocal()
    try:
        return session.query(DocumentChunk).filter_by(document_id=document_id).order_by(DocumentChunk.chunk_index).all()
    finally:
        session.close()


def _write(tmp_path, data: bytes, name="sample.pdf"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------- tables

def test_table_is_indexed_with_its_page_and_can_be_found(client, llm):
    response = upload_pdf(client, name="specs.pdf", data=table_pdf()).json()
    document = response["document"]
    assert document["processing_status"] == "ready"
    assert document["table_count"] == 1

    table_chunks = [c for c in _chunks(document["id"]) if c.content.startswith("Table on page 2")]
    assert len(table_chunks) == 1
    assert table_chunks[0].page_number == 2
    assert "XR-700 | 1100 W | 3 years" in table_chunks[0].content

    llm.reply = '{"answer": "XR-700 uses 1100 W.", "source_ids": ["S1"]}'
    answer = client.post("/api/chat", json={"question": "What is the power of XR-700?", "document_ids": [document["id"]]})
    assert answer.status_code == 200, answer.text
    cited_pages = {source["page_number"] for source in answer.json()["assistant_message"]["sources"]}
    assert 2 in cited_pages


def test_pdf_without_tables_has_no_table_chunks(client):
    document = upload_pdf(client, ["Plain text about motor power and the warranty of the device."], name="plain.pdf").json()["document"]
    assert document["processing_status"] == "ready"
    assert document["table_count"] == 0
    assert not any(c.content.startswith("Table on page") for c in _chunks(document["id"]))


def test_a_table_search_failure_keeps_the_text_indexed(client, monkeypatch):
    def broken_open(*args, **kwargs):
        raise RuntimeError("damaged table structure")

    monkeypatch.setattr(pdf_service.pdfplumber, "open", broken_open)
    document = upload_pdf(client, ["Motor power is 750 watts and the warranty lasts two years."], name="text.pdf").json()["document"]
    assert document["processing_status"] == "ready"
    assert document["table_count"] == 0
    assert document["total_chunks"] >= 1


def test_table_search_stops_at_the_time_budget(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "table_time_budget_seconds", -1.0)  # budget already used up
    document = upload_pdf(client, name="budget.pdf", data=table_pdf()).json()["document"]
    assert document["processing_status"] == "ready"
    assert document["table_count"] == 0


def test_extract_tables_reports_why_it_stopped(tmp_path):
    path = _write(tmp_path, table_pdf())
    result = pdf_service.extract_tables(path, time_budget_seconds=-1.0)
    assert result.tables == []
    assert result.skipped_reason and "large" in result.skipped_reason


def test_extract_tables_finds_the_ruled_table(tmp_path):
    result = pdf_service.extract_tables(_write(tmp_path, table_pdf()), time_budget_seconds=60)
    assert len(result.tables) == 1
    assert result.tables[0].page_number == 2
    assert result.tables[0].rows[0] == ["Model", "Power", "Warranty"]


@pytest.mark.parametrize("rows, expected_none", [
    ([["only one row", "b"]], True),                                  # one row is not a table
    ([["a", "", ""], ["", "", ""]], True),                             # too few filled cells
    ([["a", "b"], ["c", "d", "e"]], False),                           # ragged rows are padded
])
def test_table_filter_rejects_non_tables(rows, expected_none):
    result = pdf_service._usable_table(rows)
    assert (result is None) == expected_none
    if result is not None:
        assert all(len(row) == max(len(r) for r in result) for row in result)


# ---------------------------------------------------------------- OCR detection

def test_scanned_pdf_says_tesseract_is_missing_and_ocr_is_disabled(client, monkeypatch):
    monkeypatch.setattr(ocr_service.shutil, "which", lambda name: None)
    document = upload_pdf(client, [""], name="scan.pdf").json()["document"]
    assert document["processing_status"] == "needs_ocr"
    assert "Tesseract is not installed" in document["error_message"]
    assert "OCR is disabled" in document["error_message"]


def test_when_tesseract_is_found_the_message_still_says_ocr_is_not_run(client, monkeypatch):
    monkeypatch.setattr(ocr_service.shutil, "which", lambda name: "C:/tools/tesseract.exe")
    document = upload_pdf(client, [""], name="scan2.pdf").json()["document"]
    assert document["processing_status"] == "needs_ocr"
    assert "does not run OCR" in document["error_message"]


def test_health_reports_ocr_detection_without_enabling_ocr(client, monkeypatch):
    monkeypatch.setattr(ocr_service.shutil, "which", lambda name: None)
    ocr = client.get("/api/health").json()["ocr"]
    assert ocr["tesseract_installed"] is False
    assert ocr["ocr_enabled"] is False


# ---------------------------------------------------------------- empty pages and extraction errors

def test_blank_pages_are_counted_and_skipped(client):
    document = upload_pdf(client, ["Motor power is 750 watts and the warranty lasts two years.", ""], name="blank.pdf").json()["document"]
    assert document["processing_status"] == "ready"
    assert document["pages_without_text"] == 1
    assert all(c.page_number == 1 for c in _chunks(document["id"]) if not c.content.startswith("Table"))


def test_one_unreadable_page_does_not_stop_the_others(tmp_path, monkeypatch):
    original = pdf_service._page_text

    def flaky(document, index):
        if index == 1:
            raise RuntimeError("corrupt page content stream")
        return original(document, index)

    monkeypatch.setattr(pdf_service, "_page_text", flaky)
    path = _write(tmp_path, make_pdf(["First page has enough words about motor power.",
                                      "Second page is unreadable in this test.",
                                      "Third page also has enough words about the warranty."]))
    extraction = pdf_service.extract_pages(path)
    assert [page.page_number for page in extraction.pages] == [1, 3]
    assert extraction.failed_pages == [2]


def test_a_pdf_where_every_page_fails_is_reported_as_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_service, "_page_text", lambda document, index: (_ for _ in ()).throw(RuntimeError("bad")))
    with pytest.raises(pdf_service.PDFProcessingError) as info:
        pdf_service.extract_pages(_write(tmp_path, make_pdf(["One page of text here for the test."])))
    assert info.value.code == "corrupt"


# ---------------------------------------------------------------- large PDFs and duplicates

def test_a_pdf_over_the_page_limit_is_refused_before_indexing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_pages", 1)
    document = upload_pdf(client, ["Page one has text about the device.", "Page two has text about the device."], name="long.pdf").json()["document"]
    assert document["processing_status"] == "too_large"
    assert document["total_chunks"] == 0


def test_the_same_file_uploaded_twice_is_indexed_once(client):
    data = make_pdf(["A unique sentence that only appears in this document for the duplicate test."])
    first = upload_pdf(client, name="once.pdf", data=data).json()["document"]
    second = upload_pdf(client, name="again.pdf", data=data).json()["document"]
    assert first["id"] == second["id"]


def test_large_documents_are_embedded_in_batches(client, monkeypatch):
    monkeypatch.setattr(rag_service, "EMBED_BATCH", 2)
    calls: list[int] = []
    original = embedding_service.embed_texts

    def counting(texts):
        calls.append(len(texts))
        return original(texts)

    monkeypatch.setattr(embedding_service, "embed_texts", counting)
    pages = [f"Sentence number {i} describes the motor and the warranty." for i in range(12)]
    document = upload_pdf(client, pages, name="batches.pdf").json()["document"]
    assert document["processing_status"] == "ready"
    assert len(calls) > 1
    assert all(size <= 2 for size in calls)


# ---------------------------------------------------------------- migration 0003

def _url(path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _columns(path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    finally:
        connection.close()


def test_migration_0003_adds_the_new_columns_on_a_fresh_database(tmp_path, monkeypatch):
    monkeypatch.setattr(migrations, "BACKUP_DIR", tmp_path / "backups")
    path = tmp_path / "fresh.db"
    migrations.run_migrations(_url(path))
    assert {"table_count", "pages_without_text"} <= _columns(path)


def test_migration_0003_keeps_existing_documents(tmp_path, monkeypatch):
    from alembic import command

    monkeypatch.setattr(migrations, "BACKUP_DIR", tmp_path / "backups")
    path = tmp_path / "existing.db"
    migrations.run_migrations(_url(path))
    command.downgrade(migrations._alembic_config(_url(path)), "0002_study_upgrade")
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO documents (id, filename, original_filename, file_path, file_hash, file_size, page_count, "
        "processing_status, total_chunks) VALUES ('doc1', 'old.pdf', 'old.pdf', 'x.pdf', 'h', 10, 2, 'ready', 5)"
    )
    connection.commit()
    connection.close()

    migrations.run_migrations(_url(path))

    connection = sqlite3.connect(path)
    row = connection.execute("SELECT filename, total_chunks, table_count, pages_without_text FROM documents WHERE id='doc1'").fetchone()
    connection.close()
    assert row == ("old.pdf", 5, 0, 0)
