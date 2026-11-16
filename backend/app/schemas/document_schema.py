"""Pydantic schemas for documents and summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    original_filename: str
    file_size: int
    file_hash: str
    page_count: int
    processing_status: str
    error_message: str | None = None
    total_chunks: int
    table_count: int = 0
    pages_without_text: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]
    total: int


class SummaryRequest(BaseModel):
    mode: Literal["overview", "chapters"] = "overview"


class ChapterSummary(BaseModel):
    title: str
    page_start: int
    summary: str


class SummaryResponse(BaseModel):
    document_id: str
    filename: str
    mode: Literal["overview", "chapters"]
    summary: str | None = None
    chapters: list[ChapterSummary] = Field(default_factory=list)
    note: str | None = None
