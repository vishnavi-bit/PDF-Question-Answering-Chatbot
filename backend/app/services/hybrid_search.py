"""
Hybrid retrieval: meaning-based search (ChromaDB) combined with keyword search (BM25).

How scores are combined
- Semantic and keyword scores are NOT on the same scale, so they are never added together.
  Each method only contributes its RANK, using reciprocal rank fusion:
      fused(chunk) = sum over methods of 1 / (60 + rank)
  A chunk found by both methods, near the top, scores highest.
- The "is this relevant at all?" decision uses the SEMANTIC similarity of the best match
  (the same threshold as before). Keyword matches are allowed through only when several
  different question words appear together in a chunk (exact names, numbers, terms).
- Every hit keeps its document id, filename, page number and chunk index.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from sqlalchemy import select

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Document
from app.services import embedding_service, keyword_index_service, vector_store_service
from app.services.vector_store_service import VectorHit

RRF_K = 60                 # standard constant for reciprocal rank fusion
CANDIDATES_PER_METHOD = 20 # how many results each method contributes
POOL_SIZE = 20             # candidates returned to the caller (before de-duplication and reranking)
EXACT_TERMS_NEEDED = 2     # distinct question words needed for a keyword-only match to count as relevant


def selected_documents(document_ids: list[str] | None) -> list[SimpleNamespace]:
    """Ready documents to search: the selected ones, or every ready document when none are selected."""
    with SessionLocal() as session:
        query = select(Document).where(Document.processing_status == "ready")
        if document_ids:
            query = query.where(Document.id.in_(list(dict.fromkeys(document_ids))))
        return [
            SimpleNamespace(id=doc.id, file_hash=doc.file_hash, total_chunks=doc.total_chunks, filename=doc.filename)
            for doc in session.scalars(query).all()
        ]


def fuse(semantic: list[VectorHit], keyword_ids: list[str]) -> dict[str, float]:
    """Reciprocal rank fusion. Returns a score per vector id (higher = better)."""
    scores: dict[str, float] = {}
    for rank, hit in enumerate(semantic, start=1):
        scores[hit.vector_id] = scores.get(hit.vector_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, vector_id in enumerate(keyword_ids, start=1):
        scores[vector_id] = scores.get(vector_id, 0.0) + 1.0 / (RRF_K + rank)
    return scores


def retrieve(question: str, top_k: int, document_ids: list[str] | None, min_similarity: float) -> list[VectorHit]:
    """Candidate chunks for a question, best first. Empty when nothing is relevant enough."""
    documents = selected_documents(document_ids)
    if not documents:
        return []

    query_vector = embedding_service.embed_query(question)
    semantic = vector_store_service.search(
        query_vector,
        top_k=max(CANDIDATES_PER_METHOD, top_k),
        document_ids=[doc.id for doc in documents],
    )
    keyword = keyword_index_service.search(question, documents, top_n=CANDIDATES_PER_METHOD)

    best_semantic = semantic[0].similarity if semantic else 0.0
    exact_keyword_match = any(hit.matched_terms >= EXACT_TERMS_NEEDED for hit in keyword[:3])
    if best_semantic < min_similarity and not exact_keyword_match:
        return []  # nothing related: the caller answers "not found" without calling Gemini

    scores = fuse(semantic, [hit.vector_id for hit in keyword])
    by_id: dict[str, VectorHit] = {hit.vector_id: hit for hit in semantic}
    keyword_only = [hit for hit in keyword if hit.vector_id not in by_id]
    if keyword_only:
        # keyword-only chunks have no semantic similarity yet: compute it from their stored vectors
        stored = vector_store_service.get_embeddings([hit.vector_id for hit in keyword_only])
        for hit in keyword_only:
            vector = stored.get(hit.vector_id)
            similarity = float(np.dot(np.asarray(query_vector), np.asarray(vector))) if vector is not None else 0.0
            by_id[hit.vector_id] = VectorHit(
                vector_id=hit.vector_id,
                document_id=hit.document_id,
                filename=hit.filename,
                page_number=hit.page_number,
                chunk_index=hit.chunk_index,
                text=hit.text,
                similarity=round(similarity, 4),
                match="keyword",
            )

    # any chunk with an exact keyword match may be a candidate; the gate above decided relevance
    keyword_ids = {hit.vector_id for hit in keyword if hit.matched_terms >= 1}
    semantic_ids = {hit.vector_id for hit in semantic}
    results: list[VectorHit] = []
    for vector_id in sorted(scores, key=lambda key: scores[key], reverse=True):
        hit = by_id[vector_id]
        if hit.similarity < min_similarity and vector_id not in keyword_ids:
            continue  # weak semantic match with no exact keyword support: not sent to Gemini
        hit.match = "both" if vector_id in semantic_ids and vector_id in {h.vector_id for h in keyword} else (
            "semantic" if vector_id in semantic_ids else "keyword"
        )
        hit.fused = round(scores[vector_id], 6)
        results.append(hit)
        if len(results) >= POOL_SIZE:
            break
    return results
