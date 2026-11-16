"""
ChromaDB vector storage (persistent on disk).

Each chunk is stored with:
- id:        "<document_id>:<chunk_index>"  (so re-adding a chunk never duplicates it)
- embedding: the vector computed by embedding_service
- document:  the original chunk text
- metadata:  document_id, filename, page_number, chunk_index
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

import chromadb

from app.core.config import get_settings
from app.services.chunking_service import TextChunk

logger = logging.getLogger(__name__)

_client: Any = None
_lock = threading.Lock()
BATCH_SIZE_LIMIT = 1000  # chunks per ChromaDB write


@dataclass
class VectorHit:
    vector_id: str
    document_id: str
    filename: str
    page_number: int
    chunk_index: int
    text: str
    similarity: float  # 1.0 = identical meaning, 0 = unrelated (cosine similarity)
    match: str = "semantic"   # how it was found: semantic, keyword or both (Phase 3)
    fused: float = 0.0         # combined rank score from hybrid search (Phase 3)


def make_vector_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}:{chunk_index}"


def _get_collection() -> Any:
    global _client
    settings = get_settings()
    with _lock:
        if _client is None:
            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_client() -> None:
    """Forget the cached client (used by tests after changing the storage folder)."""
    global _client
    with _lock:
        _client = None


def add_chunks(
    document_id: str,
    filename: str,
    chunks: list[TextChunk],
    embeddings: list[list[float]],
) -> list[str]:
    if len(chunks) != len(embeddings):
        raise ValueError("Every chunk needs exactly one embedding")
    if not chunks:
        return []

    ids = [make_vector_id(document_id, chunk.chunk_index) for chunk in chunks]
    metadatas = [
        {
            "document_id": document_id,
            "filename": filename,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
        }
        for chunk in chunks
    ]
    # upsert = insert, or replace if the same id already exists (no duplicates).
    # ChromaDB refuses very large single writes (about 5,461 items), so write in batches.
    collection = _get_collection()
    batch_size = min(BATCH_SIZE_LIMIT, _max_batch_size())
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=[chunk.content for chunk in chunks[start:end]],
            metadatas=metadatas[start:end],
        )
    return ids


def _max_batch_size() -> int:
    global _client
    _get_collection()  # makes sure the client exists
    return int(_client.get_max_batch_size())


def delete_document_vectors(document_id: str) -> None:
    _get_collection().delete(where={"document_id": document_id})


def search(
    query_embedding: list[float],
    top_k: int,
    document_ids: list[str] | None = None,
) -> list[VectorHit]:
    """Find the most similar chunks. Optionally only inside the given documents."""
    collection = _get_collection()
    if collection.count() == 0 or top_k < 1:
        return []

    where: dict[str, Any] | None = None
    if document_ids:
        where = {"document_id": document_ids[0]} if len(document_ids) == 1 else {"document_id": {"$in": document_ids}}

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits: list[VectorHit] = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for vector_id, text, meta, distance in zip(ids, documents, metadatas, distances):
        hits.append(
            VectorHit(
                vector_id=vector_id,
                document_id=str(meta["document_id"]),
                filename=str(meta["filename"]),
                page_number=int(meta["page_number"]),
                chunk_index=int(meta["chunk_index"]),
                text=text,
                similarity=round(1.0 - float(distance), 4),
            )
        )
    return hits


def count_vectors() -> int:
    return _get_collection().count()


def get_embeddings(vector_ids: list[str]) -> dict[str, list[float]]:
    """Stored vectors for the given ids (read only). Unknown ids are left out."""
    if not vector_ids:
        return {}
    result = _get_collection().get(ids=vector_ids, include=["embeddings"])
    found: dict[str, list[float]] = {}
    for vector_id, embedding in zip(result.get("ids", []), result.get("embeddings", []) or []):
        if embedding is not None:
            found[vector_id] = [float(value) for value in embedding]
    return found
