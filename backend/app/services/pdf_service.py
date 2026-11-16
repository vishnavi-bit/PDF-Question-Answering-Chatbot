"""
PDF text and table extraction.

Text: PyMuPDF. Keeps page numbers (1-based) and detects problem PDFs:
- password protected   -> code "password_protected"
- damaged / unreadable -> code "corrupt"
- no pages             -> code "empty"
- too many pages       -> code "too_large"
- scanned (no text)    -> code "needs_ocr"

Tables: pdfplumber (Phase 7). Tables with a ruled grid are turned into text rows, for example
"Model | Power", and indexed with their page number so they can be searched and cited.
A table that cannot be read is skipped. It never stops the rest of the PDF from being indexed.

Pages without text (blank pages or scanned images) are counted and reported. OCR is not run
here; see ocr_service.py.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pymupdf

from app.services import ocr_service

logger = logging.getLogger(__name__)

# Below this many characters in total we treat the PDF as scanned / image-only.
MIN_TEXT_CHARS = 30

# Table limits: keep table text small so one table cannot dominate a chunk.
MAX_TABLE_ROWS = 200
MAX_TABLE_CHARS = 4000
MIN_TABLE_ROWS = 2
MIN_TABLE_COLUMNS = 2
MIN_FILLED_CELLS = 4


class PDFProcessingError(Exception):
    """A PDF cannot be indexed. `code` is stored as the document status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExtractedPage:
    page_number: int
    text: str


@dataclass
class PDFExtraction:
    page_count: int
    pages: list[ExtractedPage]
    pages_without_text: list[int] = field(default_factory=list)  # blank or image-only pages
    failed_pages: list[int] = field(default_factory=list)        # pages whose text could not be read

    @property
    def total_chars(self) -> int:
        return sum(len(page.text) for page in self.pages)


@dataclass
class ExtractedTable:
    page_number: int
    rows: list[list[str]]

    def to_text(self) -> str:
        lines = [" | ".join(row) for row in self.rows]
        return f"Table on page {self.page_number}:\n" + "\n".join(lines)


@dataclass
class TableExtraction:
    tables: list[ExtractedTable]
    failed_pages: list[int] = field(default_factory=list)
    skipped_reason: str | None = None  # why not every page was checked, if any


def clean_text(raw: str) -> str:
    """Tidy up text pulled out of a PDF."""
    text = raw.replace("\x00", "").replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)           # join words hyphenated over lines
    text = re.sub(r"[ \t\f\v]+", " ", text)             # collapse spaces
    text = re.sub(r" *\n *", "\n", text)                # trim spaces around line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)              # at most one blank line
    return text.strip()


def _page_text(document: pymupdf.Document, index: int) -> str:
    """Text of one page. Kept separate so tests can make a single page fail."""
    return clean_text(document[index].get_text("text"))


def extract_pages(path: Path, max_pages: int | None = None) -> PDFExtraction:
    """Read every page of a PDF and return its cleaned text."""
    try:
        document = pymupdf.open(path)
    except Exception as exc:  # PyMuPDF raises several exception types
        logger.warning("PyMuPDF could not open the file: %s", type(exc).__name__)
        raise PDFProcessingError("corrupt", "The file could not be read. It may be damaged.") from exc

    try:
        if document.needs_pass:
            raise PDFProcessingError(
                "password_protected",
                "This PDF is password protected. Remove the password and upload it again.",
            )
        if document.page_count == 0:
            raise PDFProcessingError("empty", "This PDF has no pages.")
        if max_pages is not None and document.page_count > max_pages:
            # refuse before reading every page
            raise PDFProcessingError(
                "too_large",
                f"This PDF has {document.page_count} pages. The limit is {max_pages} pages.",
            )

        pages: list[ExtractedPage] = []
        without_text: list[int] = []
        failed: list[int] = []
        for index in range(document.page_count):
            page_number = index + 1
            try:
                text = _page_text(document, index)
            except Exception as exc:  # one damaged page must not stop the others
                logger.warning("Text could not be read from page %s: %s", page_number, type(exc).__name__)
                failed.append(page_number)
                continue
            if not text:
                without_text.append(page_number)
            pages.append(ExtractedPage(page_number=page_number, text=text))

        if failed and len(failed) == document.page_count:
            raise PDFProcessingError("corrupt", "Text could not be extracted from this PDF.")
        extraction = PDFExtraction(
            page_count=document.page_count,
            pages=pages,
            pages_without_text=without_text,
            failed_pages=failed,
        )
    except PDFProcessingError:
        raise
    except Exception as exc:
        logger.warning("Error while extracting PDF text: %s", type(exc).__name__)
        raise PDFProcessingError("corrupt", "Text could not be extracted from this PDF.") from exc
    finally:
        document.close()

    if extraction.total_chars < MIN_TEXT_CHARS:
        raise PDFProcessingError("needs_ocr", ocr_service.scanned_pdf_message())
    return extraction


def _clean_cell(cell: object) -> str:
    return " ".join(str(cell or "").split())


def _usable_table(rows: list[list[str]]) -> list[list[str]] | None:
    """Keep only tables that have a real grid: at least 2 rows, 2 columns and some filled cells."""
    if len(rows) < MIN_TABLE_ROWS:
        return None
    width = max(len(row) for row in rows)
    if width < MIN_TABLE_COLUMNS:
        return None
    padded = [row + [""] * (width - len(row)) for row in rows]
    filled = sum(1 for row in padded for cell in row if cell)
    if filled < MIN_FILLED_CELLS:
        return None
    return padded


def extract_tables(path: Path, time_budget_seconds: float) -> TableExtraction:
    """
    Find ruled tables on every page with pdfplumber.
    Stops after `time_budget_seconds` (large PDFs stay within a bounded time) and never raises.
    """
    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:
        logger.warning("Table search skipped: pdfplumber could not open the file (%s)", type(exc).__name__)
        return TableExtraction(tables=[], skipped_reason="The tables could not be searched in this PDF.")

    tables: list[ExtractedTable] = []
    failed: list[int] = []
    skipped_reason: str | None = None
    started = time.monotonic()
    try:
        for page in pdf.pages:
            if time.monotonic() - started > time_budget_seconds:
                skipped_reason = "Table search stopped early because this PDF is large."
                break
            try:
                found = page.extract_tables() or []
            except Exception as exc:
                logger.warning("Tables could not be read from page %s: %s", page.page_number, type(exc).__name__)
                failed.append(page.page_number)
                continue
            for raw_table in found:
                rows = [[_clean_cell(cell) for cell in row] for row in (raw_table or []) if row]
                usable = _usable_table(rows)
                if usable is None:
                    continue
                usable = usable[:MAX_TABLE_ROWS]
                table = ExtractedTable(page_number=page.page_number, rows=usable)
                if len(table.to_text()) > MAX_TABLE_CHARS:
                    table = _shorten(table)
                tables.append(table)
    finally:
        pdf.close()
    return TableExtraction(tables=tables, failed_pages=failed, skipped_reason=skipped_reason)


def _shorten(table: ExtractedTable) -> ExtractedTable:
    kept: list[list[str]] = []
    size = len(f"Table on page {table.page_number}:")
    for row in table.rows:
        line = " | ".join(row)
        if size + len(line) + 1 > MAX_TABLE_CHARS:
            break
        kept.append(row)
        size += len(line) + 1
    return ExtractedTable(page_number=table.page_number, rows=kept or table.rows[:1])


def table_pages(tables: list[ExtractedTable]) -> list[ExtractedPage]:
    """Tables as pages of text, so they can be split into chunks with their page numbers."""
    return [ExtractedPage(page_number=table.page_number, text=table.to_text()) for table in tables]
