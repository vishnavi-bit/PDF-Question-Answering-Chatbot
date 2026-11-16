"""
Embedding tests.

The real model test is skipped unless RUN_REAL_MODEL=1 is set, because it
downloads about 90 MB the first time. All other tests use the fake embedder.
"""

from __future__ import annotations

import os

import pytest

from app.services import embedding_service


def test_no_texts_returns_no_vectors_without_loading_the_model(monkeypatch):
    def fail_if_loaded():
        raise AssertionError("the model should not be loaded for empty input")

    monkeypatch.setattr(embedding_service, "_get_model", fail_if_loaded)
    assert embedding_service.embed_texts([]) == []


@pytest.mark.skipif(os.getenv("RUN_REAL_MODEL") != "1", reason="set RUN_REAL_MODEL=1 to test the real model")
def test_real_model_puts_related_sentences_closer_together(monkeypatch):
    import math

    from tests.conftest import REAL_EMBED_TEXTS

    # Replace the fake embedder from conftest with the real one (restored automatically afterwards).
    monkeypatch.setattr(embedding_service, "embed_texts", REAL_EMBED_TEXTS)
    vectors = embedding_service.embed_texts(
        ["How do I reset my password?", "Steps to change a forgotten password", "The weather is sunny today"]
    )

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))

    assert len(vectors[0]) == 384  # all-MiniLM-L6-v2 output size
    assert cosine(vectors[0], vectors[1]) > cosine(vectors[0], vectors[2])
