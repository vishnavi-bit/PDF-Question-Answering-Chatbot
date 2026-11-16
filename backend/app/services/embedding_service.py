"""
Embeddings with a Hugging Face sentence-transformers model.

An embedding is a list of numbers (a vector) that represents the meaning of a
text. Texts with similar meaning get vectors that point in similar directions,
so we can search by meaning instead of exact words.

The model is loaded once and reused (it is slow to load). Documents and
questions MUST use the same model, otherwise the numbers cannot be compared.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when the embedding model cannot load or fails to run."""


_model: Any = None
_model_lock = threading.Lock()


def _get_model() -> Any:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # check again inside the lock
                model_name = get_settings().embedding_model
                try:
                    from sentence_transformers import SentenceTransformer  # heavy import, done lazily

                    logger.info("Loading embedding model %s (first time may download it)", model_name)
                    _model = SentenceTransformer(model_name)
                except Exception as exc:
                    logger.exception("Could not load embedding model")
                    raise EmbeddingError(
                        f"The embedding model '{model_name}' could not be loaded. "
                        "On first use it is downloaded from Hugging Face, so check your internet connection."
                    ) from exc
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn many texts into normalised vectors (unit length, for cosine similarity)."""
    if not texts:
        return []
    model = _get_model()
    try:
        vectors = model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    except Exception as exc:
        logger.exception("Embedding generation failed")
        raise EmbeddingError("Embedding generation failed. Please try again.") from exc
    return [[float(value) for value in vector] for vector in vectors]


def embed_query(text: str) -> list[float]:
    """Embed one question. Uses the same model as the document chunks."""
    return embed_texts([text])[0]
