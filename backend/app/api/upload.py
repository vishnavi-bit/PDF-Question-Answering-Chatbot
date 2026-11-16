"""Upload endpoint: POST /api/documents/upload"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.connection import get_db
from app.schemas.document_schema import DocumentOut
from app.schemas.upload_schema import UploadResponse
from app.services import rag_service
from app.services.rag_service import IngestError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])

READ_CHUNK_BYTES = 1024 * 1024


def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Read the upload in pieces and stop as soon as it is too large."""
    buffer = bytearray()
    while True:
        chunk = upload.file.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"The file is larger than {get_settings().max_upload_size_mb} MB.",
            )
    return bytes(buffer)


@router.post("/documents/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> UploadResponse:
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted (the file name must end with .pdf).")

    data = _read_limited(file, get_settings().max_upload_bytes)
    try:
        document, duplicate = rag_service.ingest_pdf(db, data, filename)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if duplicate:
        message = "This PDF was already uploaded, so the existing copy is being used."
    elif document.processing_status == "ready":
        message = f"Indexed {document.total_chunks} text chunks from {document.page_count} pages."
    else:
        message = document.error_message or "The PDF could not be processed."
    return UploadResponse(document=DocumentOut.model_validate(document), duplicate=duplicate, message=message)
