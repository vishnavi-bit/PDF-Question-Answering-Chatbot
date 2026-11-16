"""Tests for the context-size rules: duplicate removal, the character cap and history limits."""

from __future__ import annotations

from app.services import rag_service
from app.services.rag_service import HISTORY_CHARS_PER_MESSAGE, MAX_CONTEXT_CHARS, select_context_hits
from app.services.vector_store_service import VectorHit


def _hit(index: int, text: str, similarity: float = 0.9) -> VectorHit:
    return VectorHit(
        vector_id=f"d:{index}",
        document_id="d",
        filename="manual.pdf",
        page_number=index + 1,
        chunk_index=index,
        text=text,
        similarity=similarity,
    )


def test_overlapping_neighbour_chunk_is_dropped():
    first = "Alpha warranty text. " * 40                      # about 840 characters
    second = first[-150:] + "Beta cleaning text. " * 20      # shares the last 150 characters of the first
    selected, duplicates = select_context_hits([_hit(0, first), _hit(1, second)])

    assert len(selected) == 1
    assert duplicates == 1
    assert selected[0].chunk_index == 0


def test_distinct_chunks_are_all_kept():
    selected, duplicates = select_context_hits(
        [_hit(0, "Warranty covers motor defects for two years. " * 5), _hit(1, "Cleaning: wash the jar with warm water. " * 5)]
    )
    assert len(selected) == 2
    assert duplicates == 0


def test_total_context_is_capped():
    hits = [_hit(i, f"Distinct topic number {i}: " + ("word " * 200)) for i in range(10)]  # about 1000 chars each
    selected, _ = select_context_hits(hits)

    total = sum(len(hit.text) for hit in selected)
    assert total <= MAX_CONTEXT_CHARS
    assert 1 <= len(selected) < 10
    # the strongest (first) chunk is always kept
    assert selected[0].chunk_index == 0


def test_page_numbers_are_preserved_for_kept_chunks():
    selected, _ = select_context_hits([_hit(3, "Safety notice about the blades on page four. " * 3)])
    assert selected[0].page_number == 4


def test_history_keeps_only_the_last_two_exchanges():
    history = []
    for number in range(6):
        history.append(("user", f"Question {number}"))
        history.append(("assistant", f"Answer {number}"))
    messages = rag_service.build_history_messages(history)

    assert len(messages) == rag_service.HISTORY_MESSAGE_LIMIT
    assert messages[0]["content"] == "Question 4"
    assert messages[-1]["content"] == "Answer 5"


def test_long_earlier_answers_are_shortened():
    long_answer = "x" * 2000
    messages = rag_service.build_history_messages([("user", "Q"), ("assistant", long_answer)])
    assert len(messages[1]["content"]) <= HISTORY_CHARS_PER_MESSAGE + 3
    assert messages[1]["content"].endswith("...")
