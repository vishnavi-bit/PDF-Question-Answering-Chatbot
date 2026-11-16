"""PDF text extraction tests (PyMuPDF)."""

from __future__ import annotations

import pytest


from app.services.pdf_service import PDFProcessingError, clean_text, extract_pages
from tests.helpers import make_password_pdf, make_pdf, make_scanned_pdf


def _write(tmp_path, data: bytes, name: str = "file.pdf"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_extracts_text_and_keeps_page_numbers(tmp_path):
    path = _write(tmp_path, make_pdf(["Alpha page text here.", "Beta page text here."]))

    extraction = extract_pages(path)

    assert extraction.page_count == 2
    assert [page.page_number for page in extraction.pages] == [1, 2]
    assert "Alpha" in extraction.pages[0].text
    assert "Beta" in extraction.pages[1].text


def test_scanned_pdf_without_text_is_flagged_as_needing_ocr(tmp_path):
    path = _write(tmp_path, make_scanned_pdf())

    with pytest.raises(PDFProcessingError) as info:
        extract_pages(path)

    assert info.value.code == "needs_ocr"
    assert "OCR" in info.value.message


def test_password_protected_pdf_is_detected(tmp_path):
    path = _write(tmp_path, make_password_pdf())

    with pytest.raises(PDFProcessingError) as info:
        extract_pages(path)

    assert info.value.code == "password_protected"


def test_damaged_file_is_reported_as_corrupt(tmp_path):
    path = _write(tmp_path, b"%PDF-1.4 this is not really a pdf")

    with pytest.raises(PDFProcessingError) as info:
        extract_pages(path)

    assert info.value.code == "corrupt"


def test_clean_text_joins_hyphenated_words_and_collapses_blank_lines():
    raw = "Infor-\nmation   retrieval\r\n\n\n\nnext\x00 part"
    cleaned = clean_text(raw)
    assert "Information retrieval" in cleaned
    assert "\n\n\n" not in cleaned
    assert "\x00" not in cleaned
