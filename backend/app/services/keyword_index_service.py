"""
Keyword search (BM25) over the chunks of the selected PDFs.

The chunk text is already stored in SQLite, so the index is built from there and ChromaDB
is never changed. Each set of selected PDFs gets its own index, cached in memory. The cache
key includes each PDF's file hash and chunk count, so adding or deleting a PDF rebuilds it.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass

from rank_bm25 import BM25Plus
from sqlalchemy import select

from app.database.connection import SessionLocal
from app.database.models import Document, DocumentChunk
from app.services.text_tokens import content_tokens, tokenize

MAX_CACHED_INDEXES = 8


@dataclass
class KeywordHit:
    vector_id: str
    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    text: str
    score: float          # BM25 score (higher = more matching words)
    matched_terms: int    # how many different question words appear in the chunk


@dataclass
class _Index:
    bm25: BM25Plus | None
    rows: list[dict]


_cache: "OrderedDict[tuple, _Index]" = OrderedDict()
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _index_key(documents: list[Document]) -> tuple:
    return tuple(sorted((doc.id, doc.file_hash, doc.total_chunks) for doc in documents))


def _build(documents: list[Document]) -> _Index:
    document_ids = [doc.id for doc in documents]
    with SessionLocal() as session:
        rows_db = session.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        ).all()
    rows = [
        {
            "vector_id": chunk.vector_id,
            "document_id": chunk.document_id,
            "filename": filename,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "text": chunk.content,
            "tokens": tokenize(chunk.content),
        }
        for chunk, filename in rows_db
    ]
    if not rows:
        return _Index(bm25=None, rows=[])
    # BM25Plus keeps a positive score for every matching word, even in small document sets
    return _Index(bm25=BM25Plus([row["tokens"] for row in rows]), rows=rows)


def _get_index(documents: list[Document]) -> _Index:
    key = _index_key(documents)
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached
    built = _build(documents)  # built outside the lock: it can take a moment for big PDFs
    with _lock:
        _cache[key] = built
        _cache.move_to_end(key)
        while len(_cache) > MAX_CACHED_INDEXES:
            _cache.popitem(last=False)
    return built


def search(question: str, documents: list[Document], top_n: int) -> list[KeywordHit]:
    """Best keyword matches inside the given documents only (score > 0), best first."""
    if not documents or top_n < 1:
        return []
    index = _get_index(documents)
    if index.bm25 is None:
        return []
    query_tokens = content_tokens(question)
    if not query_tokens:
        return []
    scores = index.bm25.get_scores(query_tokens)
    wanted = set(query_tokens)
    ranked = sorted(range(len(scores)), key=lambda position: scores[position], reverse=True)
    hits: list[KeywordHit] = []
    for position in ranked:
        if scores[position] <= 0 or len(hits) >= top_n:
            break
        row = index.rows[position]
        matched = len(wanted & set(row["tokens"]))
        hits.append(
            KeywordHit(
                vector_id=row["vector_id"],
                document_id=row["document_id"],
                filename=row["filename"],
                page_number=row["page_number"],
                chunk_index=row["chunk_index"],
                text=row["text"],
                score=float(scores[position]),
                matched_terms=matched,
            )
        )
    return hits
