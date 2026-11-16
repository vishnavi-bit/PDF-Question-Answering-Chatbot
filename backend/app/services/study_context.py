"""
Chooses which PDF text is sent to Gemini for study features.

Study generation does not search for one question, so it needs broad coverage of
the selected PDFs while keeping the request small:
- every selected PDF gets an equal share of the character budget (fair coverage);
- inside a PDF, chunks are sampled evenly from start to end;
- topic explanations use the existing semantic search instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import Document, DocumentChunk
from app.services import retrieval_service

STUDY_CHAR_BUDGET = 12000   # total excerpt text for one study request (about 3,000 tokens)
TOPIC_TOP_K = 6


class StudyError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class StudyExcerpt:
    source_id: str          # S1, S2, ... used by the model and for citations
    document_id: str
    filename: str
    page_number: int
    text: str
    section: str | None = None   # chapter heading, when known


def ready_documents(db: Session, document_ids: list[str]) -> list[Document]:
    """Selected ready documents, or every ready document when nothing is selected."""
    query = select(Document).where(Document.processing_status == "ready").order_by(Document.created_at, Document.id)
    if document_ids:
        query = query.where(Document.id.in_(list(dict.fromkeys(document_ids))))
    documents = list(db.scalars(query).all())
    if document_ids and len(documents) < len(set(document_ids)):
        raise StudyError(404, "document_not_found", "One or more selected PDFs were not found or are not ready.")
    if not documents:
        raise StudyError(400, "no_documents", "No ready PDFs are available. Upload a PDF and wait until it is Ready.")
    return documents


def _sample_evenly(chunks: list[DocumentChunk], char_budget: int) -> list[DocumentChunk]:
    if sum(len(chunk.content) for chunk in chunks) <= char_budget:
        return chunks
    average = max(1, sum(len(chunk.content) for chunk in chunks) // len(chunks))
    wanted = max(1, char_budget // average)
    step = max(1, math.ceil(len(chunks) / wanted))
    picked: list[DocumentChunk] = []
    used = 0
    for chunk in chunks[::step]:
        if used + len(chunk.content) > char_budget:
            break
        picked.append(chunk)
        used += len(chunk.content)
    return picked


def select_study_excerpts(db: Session, document_ids: list[str], char_budget: int = STUDY_CHAR_BUDGET) -> list[StudyExcerpt]:
    """Evenly sampled excerpts from every selected PDF, sharing the budget equally."""
    documents = ready_documents(db, document_ids)
    per_document = max(1, char_budget // len(documents))
    excerpts: list[StudyExcerpt] = []
    for document in documents:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )
        for chunk in _sample_evenly(chunks, per_document):
            excerpts.append(
                StudyExcerpt(
                    source_id=f"S{len(excerpts) + 1}",
                    document_id=document.id,
                    filename=document.filename,
                    page_number=chunk.page_number,
                    text=chunk.content,
                )
            )
    if not excerpts:
        raise StudyError(400, "no_text", "The selected PDFs have no indexed text to study.")
    return excerpts


def select_topic_excerpts(db: Session, topic: str, document_ids: list[str]) -> list[StudyExcerpt]:
    """Excerpts most related to a topic, found with the existing semantic search."""
    documents = ready_documents(db, document_ids)
    settings = get_settings()
    hits = retrieval_service.retrieve_chunks(
        topic,
        top_k=TOPIC_TOP_K,
        document_ids=[document.id for document in documents],
        min_similarity=settings.min_similarity,
    )
    return [
        StudyExcerpt(
            source_id=f"S{number}",
            document_id=hit.document_id,
            filename=hit.filename,
            page_number=hit.page_number,
            text=hit.text,
        )
        for number, hit in enumerate(hits, start=1)
    ]


def excerpt_map(excerpts: list[StudyExcerpt]) -> dict[str, StudyExcerpt]:
    return {excerpt.source_id: excerpt for excerpt in excerpts}
