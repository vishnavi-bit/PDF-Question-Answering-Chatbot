"""
Security helpers: safe filenames, PDF validation, secure deletion and
path-traversal protection.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]")


def sanitize_filename(name: str | None, default: str = "document.pdf") -> str:
    """Keep only a safe, short display name (no folders, no odd characters)."""
    if not name:
        return default
    # Drop any folder parts a browser or attacker may have sent ("..\\..\\x.pdf").
    base = re.split(r"[\\/]", name)[-1]
    base = _UNSAFE_CHARS.sub("_", base).strip(" .")
    if not base:
        return default
    if not base.lower().endswith(".pdf"):
        base = f"{base}.pdf"
    return base[:200]


def new_document_id() -> str:
    return uuid.uuid4().hex


def is_pdf_bytes(data: bytes) -> bool:
    """A real PDF starts with '%PDF-' near the beginning of the file."""
    return PDF_MAGIC in data[:1024]


def ensure_inside(base_dir: Path, candidate: Path) -> Path:
    """Raise ValueError if candidate is not inside base_dir (path traversal guard)."""
    base = base_dir.resolve()
    resolved = candidate.resolve()
    if base != resolved and base not in resolved.parents:
        raise ValueError("Path is outside the allowed storage folder")
    return resolved


def secure_delete_file(path: Path) -> None:
    """Overwrite a file with zeros before removing it. Missing files are ignored."""
    try:
        if not path.exists():
            return
        size = path.stat().st_size
        with open(path, "r+b") as handle:
            handle.write(b"\x00" * size)
            handle.flush()
            os.fsync(handle.fileno())
        path.unlink()
    except OSError:
        logger.warning("Could not securely delete a stored file", exc_info=True)
