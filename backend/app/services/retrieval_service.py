"""
Retrieval: turn a question into an embedding, find similar chunks, and drop
the weak matches so unrelated questions do not get misleading answers.
"""

from __future__ import annotations

from app.services import embedding_service, vector_store_service
from app.services.vector_store_service import VectorHit


def retrieve_chunks(
    question: str,
    top_k: int,
    document_ids: list[str] | None,
    min_similarity: float,
) -> list[VectorHit]:
    """
    Candidate chunks for a question, best first (Phase 3: semantic + keyword hybrid search).
    Empty when nothing is related enough. The caller decides how many to keep.
    """
    from app.services import hybrid_search

    return hybrid_search.retrieve(question, top_k, document_ids, min_similarity)
