"""
OCR detection only (Phase 7).

This app does not run OCR and never installs Tesseract. It only checks whether the `tesseract`
program is on the PATH, so that the messages shown to the user are accurate:
- Tesseract missing: scanned PDFs cannot be read, and the app says so.
- Tesseract found: the app says it found Tesseract, and that scanned pages are still not read in
  this version.
"""

from __future__ import annotations

import shutil


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def status() -> dict[str, object]:
    available = tesseract_available()
    return {
        "tesseract_installed": available,
        "ocr_enabled": False,  # this version never runs OCR
        "message": (
            "Tesseract was found, but scanned pages are not read in this version. "
            "Scanned PDFs are detected and explained."
            if available
            else "OCR is disabled because Tesseract is not installed. Scanned pages cannot be read until it is installed."
        ),
    }


def scanned_pdf_message() -> str:
    """Shown when a PDF has almost no selectable text."""
    if tesseract_available():
        return (
            "This PDF looks scanned or image-based (almost no selectable text). "
            "Tesseract was found, but this version does not run OCR, so the PDF cannot be searched yet."
        )
    return (
        "This PDF looks scanned or image-based (almost no selectable text). "
        "OCR is disabled because Tesseract is not installed, so the PDF cannot be searched. "
        "See docs/setup_guide.md if you want to install Tesseract later."
    )
