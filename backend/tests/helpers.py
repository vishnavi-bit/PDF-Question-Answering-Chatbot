"""Helper functions and fakes shared by the test files."""

from __future__ import annotations

import hashlib
import math
import re

import pymupdf
from fastapi.testclient import TestClient

FAKE_DIM = 256
# Common words are ignored by the fake embedder so they do not create false matches.
STOPWORDS = {"a", "an", "and", "are", "be", "by", "do", "for", "from", "how", "in", "is", "it",
             "of", "on", "or", "the", "to", "what", "when", "where", "which", "who", "why", "with"}


def fake_embed_texts(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-words embedding: texts sharing words get similar vectors."""
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * FAKE_DIM
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            if word in STOPWORDS:
                continue
            bucket = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % FAKE_DIM
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors


def make_pdf(pages: list[str]) -> bytes:
    """Create a PDF with one page per string (real selectable text)."""
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), text, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def make_scanned_pdf() -> bytes:
    """A PDF page with no text layer (like a scanned page)."""
    document = pymupdf.open()
    document.new_page()
    data = document.tobytes()
    document.close()
    return data


def make_password_pdf(password: str = "secret") -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), "Secret text inside a locked file.", fontsize=11)
    data = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw=password,
        user_pw=password,
    )
    document.close()
    return data


def upload_pdf(client: TestClient, pages: list[str] | None = None, name: str = "sample.pdf", data: bytes | None = None):
    content = data if data is not None else make_pdf(pages or ["Default sample text about the topic."])
    return client.post("/api/documents/upload", files={"file": (name, content, "application/pdf")})


class FakeLLM:
    """Replaces llm_service.complete. Set `reply` or `error` to control what Gemini 'does'."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.reply: str | None = None  # None = answer citing S1
        self.error: Exception | None = None

    def __call__(
        self, system: str, messages: list[dict], max_tokens: int | None = None, json_output: bool = False
    ) -> str:
        self.calls.append({"system": system, "messages": messages, "json_output": json_output})
        if self.error is not None:
            raise self.error
        if self.reply is not None:
            return self.reply
        return '{"answer": "Here is the answer from the document.", "source_ids": ["S1"]}'
