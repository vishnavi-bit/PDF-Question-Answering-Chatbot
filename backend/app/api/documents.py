"""Document endpoints: list, details, PDF file, delete and summaries."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ensure_inside
from app.database.connection import get_db
from app.database.models import Document
from app.schemas.document_schema import DocumentListResponse, DocumentOut, SummaryRequest, SummaryResponse
from app.services import rag_service, summary_service
from app.services.llm_service import LLMError

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document_or_404(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.get("", response_model=DocumentListResponse)
def list_documents(db: Session = Depends(get_db)) -> DocumentListResponse:
    documents = db.scalars(select(Document).order_by(Document.created_at.desc(), Document.id)).all()
    return DocumentListResponse(
        documents=[DocumentOut.model_validate(doc) for doc in documents],
        total=len(documents),
    )


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentOut:
    return DocumentOut.model_validate(_get_document_or_404(db, document_id))


@router.get("/{document_id}/file")
def get_document_file(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve the stored PDF so the viewer can show it."""
    document = _get_document_or_404(db, document_id)
    if document.processing_status != "ready" or not document.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This document's file is not available.")
    try:
        path = ensure_inside(get_settings().upload_dir, Path(document.file_path))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file location.") from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The stored PDF file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=document.filename, content_disposition_type="inline")


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> Response:
    document = _get_document_or_404(db, document_id)
    rag_service.delete_document_everywhere(db, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/summary", response_model=SummaryResponse)
def summarize(document_id: str, body: SummaryRequest | None = None, db: Session = Depends(get_db)) -> SummaryResponse:
    mode = body.mode if body else "overview"
    try:
        return summary_service.summarize_document(db, document_id, mode)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
