"""
Retrieval evaluation with the REAL embedding model (meaning-based questions).

Skipped unless RUN_REAL_MODEL=1, because it downloads the embedding model the first time.
It measures, for a small labelled set:
- recall@5: how often the correct page is among the top 5 chunks;
- MRR: how high the correct page ranks on average (1.0 = always first).
No Gemini calls are made here.
"""

from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.services import embedding_service, retrieval_service
from tests.conftest import REAL_EMBED_TEXTS
from tests.test_retrieval_quality import BLENDER, HOSE, PAPER

pytestmark = pytest.mark.skipif(os.getenv("RUN_REAL_MODEL") != "1", reason="set RUN_REAL_MODEL=1 to run the real-model evaluation")

# (question, expected filename, expected page) - meaning-based, not copied from the text
LABELLED = [
    ("How long does the warranty of the blender last?", "blender.pdf", 1),
    ("How much power does the blender motor have?", "blender.pdf", 2),
    ("How big is the image collection used for training?", "paper.pdf", 1),
    ("How well did the model perform on unseen data?", "paper.pdf", 2),
    ("What water pressure must the hose never exceed?", "hose.pdf", 2),
    ("How should the garden hose be kept in winter?", "hose.pdf", 2),
    ("How long is the guarantee for the garden hose?", "hose.pdf", 1),
    ("How should the blender blades be cleaned?", "blender.pdf", 2),
]


def _rank_of(expected_file, expected_page, hits):
    for position, hit in enumerate(hits, start=1):
        if hit.filename == expected_file and hit.page_number == expected_page:
            return position
    return None


def test_meaning_based_questions_find_the_right_page(client, monkeypatch, capsys):
    from tests.helpers import upload_pdf

    monkeypatch.setattr(embedding_service, "embed_texts", REAL_EMBED_TEXTS)  # the real model, for indexing AND questions
    upload_pdf(client, BLENDER, name="blender.pdf")
    upload_pdf(client, HOSE, name="hose.pdf")
    upload_pdf(client, PAPER, name="paper.pdf")

    ranks = []
    for question, filename, page in LABELLED:
        hits = retrieval_service.retrieve_chunks(question, 10, None, 0.0)
        ranks.append(_rank_of(filename, page, hits))

    found_in_top5 = [rank for rank in ranks if rank is not None and rank <= 5]
    recall_at_5 = len(found_in_top5) / len(LABELLED)
    mrr = sum((1.0 / rank) for rank in ranks if rank) / len(LABELLED)
    print(f"\nretrieval evaluation: recall@5={recall_at_5:.2f} MRR={mrr:.2f} ranks={ranks}")
    assert recall_at_5_check(recall_at_5)
    assert mrr >= 0.6


def recall_at_5_check(recall: float) -> bool:
    return recall >= 0.75
