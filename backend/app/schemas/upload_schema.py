"""Pydantic schema for the upload response."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.document_schema import DocumentOut


class UploadResponse(BaseModel):
    document: DocumentOut
    duplicate: bool = False
    message: str
