"""
Application configuration.

All configurable values come from environment variables (or from
backend/.env). Nothing secret is hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ folder (this file is backend/app/core/config.py)
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Gemini API (Google AI Studio key: https://aistudio.google.com/apikey)
    gemini_api_key: str = Field(default="", repr=False)
    # Default: gemini-3.6-flash. In live tests gemini-3.8-flash timed out (504 after ~88 s)
    # even on a 6-token prompt, while gemini-3.6-flash answered in about 1-2 s with the same key.
    # gemini-2.5-flash and gemini-2.5-flash-lite return 404: no longer available to new users.
    gemini_model: str = "gemini-3.6-flash"
    # Gemini "thinking" models also count their internal reasoning against this limit,
    # so keep it generous.
    gemini_max_output_tokens: int = 2048
    # Thinking level: minimal, low, medium or high. Empty = the model's default.
    gemini_thinking_level: str = ""
    # Seconds for ONE request to Gemini. Long documents and the model's own thinking can
    # take a while, so the limit is higher than before (was 60 s).
    gemini_timeout_seconds: float = 90.0
    # Maximum total time for one question, including retries and waits. Kept below the
    # frontend's 180 s limit so the user gets a clear message instead of a browser timeout.
    gemini_total_time_budget_seconds: float = 150.0
    # Reliability: after this many failed calls in a row (outage-type errors only),
    # calls fail fast for the cooldown period instead of waiting on Gemini again.
    gemini_failure_threshold: int = 3
    gemini_cooldown_seconds: float = 60.0
    # After a free-tier quota error, no new Gemini request is sent for this long (the quota does not recover in seconds).
    gemini_quota_cooldown_seconds: float = 300.0
    # Answers for identical prompts are reused for this long (0 turns caching off).
    # The prompt includes the excerpts, so a different PDF selection never reuses an answer.
    gemini_cache_ttl_seconds: float = 900.0
    gemini_cache_max_entries: int = 200
    # Repeated identical requests (double clicks, retries after a timeout) return the same result
    # for this long instead of creating duplicate records.
    request_dedupe_ttl_seconds: float = 120.0

    # Storage locations (relative paths are resolved from the backend/ folder)
    database_url: str = "sqlite:///./data/app.db"
    chroma_persist_directory: str = "../storage/chroma_db"
    upload_directory: str = "../storage/uploads"
    chroma_collection_name: str = "pdf_chunks"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Web
    frontend_url: str = "http://localhost:5173"
    static_directory: str = "../frontend/dist"

    # Uploads
    max_upload_size_mb: int = 20

    # Large documents: pages above this limit are refused (keeps indexing time bounded)
    max_pdf_pages: int = 1000

    # Tables (pdfplumber): ruled tables are indexed with their page number.
    # Table search stops after this many seconds, so very large PDFs keep a bounded indexing time.
    enable_table_extraction: bool = True
    table_time_budget_seconds: float = 120.0

    # Chunking (characters)
    chunk_size: int = 1000
    chunk_overlap: int = 150

    # Retrieval
    min_similarity: float = 0.25
    max_question_chars: int = 2000
    # Phase 3: Gemini reranking of the top candidates (turn off to save calls)
    rerank_enabled: bool = True
    # Phase 3: share of a sentence's words that must appear in the cited PDF text
    verification_threshold: float = 0.6

    # ---- helpers -------------------------------------------------------
    def resolve_path(self, value: str) -> Path:
        """Turn a configured path into an absolute path (relative to backend/)."""
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()

    @property
    def upload_dir(self) -> Path:
        return self.resolve_path(self.upload_directory)

    @property
    def chroma_dir(self) -> Path:
        return self.resolve_path(self.chroma_persist_directory)

    @property
    def static_dir(self) -> Path:
        return self.resolve_path(self.static_directory)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    return settings
