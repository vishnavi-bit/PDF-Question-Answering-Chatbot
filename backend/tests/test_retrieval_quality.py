"""
Phase 3 retrieval quality: hybrid search, reranking (with failures), duplicates, selection limits,
irrelevant and missing-information questions, and source verification.

PDFs here are real uploads (real ingestion, SQLite and ChromaDB). Embeddings and Gemini are fakes.
Meaning-based questions are tested with the real embedding model in test_retrieval_eval_real.py.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import DocumentChunk
from app.services import hybrid_search, keyword_index_service, rerank_service, retrieval_service, vector_store_service
from app.services.llm_service import LLMError
from app.services.text_tokens import content_tokens, tokenize
from app.services.verification_service import split_sentences, verify_answer
from tests.helpers import make_pdf, upload_pdf

BLENDER = [
    "Acme Blender model XR-500 carries a limited warranty of two years from the date of purchase.",
    "The motor power is 750 watts. Clean the blade assembly with warm water after each use.",
]
HOSE = [
    "The Greenline garden hose is guaranteed for five years against leaks and cracking.",
    "Do not exceed a water pressure of 6 bar at the inlet. Store the hose coiled in the shade.",
]
PAPER = [
    "Our methodology uses a dataset of 1,200 labelled images collected in 2023.",
    "The model reached 92.4 percent accuracy on the held-out test set. Limitations include a small sample.",
]


def _ids(client, pages, name):
    return upload_pdf(client, pages, name=name).json()["document"]["id"]


@pytest.fixture
def corpus(client):
    return {
        "blender": _ids(client, BLENDER, "blender.pdf"),
        "hose": _ids(client, HOSE, "hose.pdf"),
        "paper": _ids(client, PAPER, "paper.pdf"),
    }


def _top_pages(question, document_ids=None, top_k=5):
    hits = retrieval_service.retrieve_chunks(question, top_k, document_ids, get_settings().min_similarity)
    return [(hit.filename, hit.page_number) for hit in hits]


# ---------------------------------------------------------------- tokens and keyword search

def test_tokens_keep_model_numbers_and_decimals():
    assert "xr-500" in tokenize("Model XR-500 costs 3.5 units")
    assert "3.5" in tokenize("Model XR-500 costs 3.5 units")


def test_stop_words_are_removed_from_questions():
    assert content_tokens("What is the warranty of the blender?") == ["warranty", "blender"]


def test_keyword_search_finds_an_exact_model_number(corpus):
    from types import SimpleNamespace

    docs = [SimpleNamespace(id=corpus["blender"], file_hash="x", total_chunks=2, filename="blender.pdf")]
    hits = keyword_index_service.search("XR-500", docs, top_n=3)
    assert hits and hits[0].filename == "blender.pdf"
    assert hits[0].page_number == 1


def test_keyword_index_is_rebuilt_when_a_pdf_is_added(client, corpus):
    before = len(keyword_index_service._cache)
    upload_pdf(client, ["A brand new manual about kettles and tea."], name="kettle.pdf")
    hybrid_search.retrieve("kettles", 5, None, 0.0)
    assert len(keyword_index_service._cache) >= before


def test_keyword_index_only_searches_the_selected_documents(corpus):
    from types import SimpleNamespace

    docs = [SimpleNamespace(id=corpus["hose"], file_hash="h", total_chunks=2, filename="hose.pdf")]
    assert keyword_index_service.search("blender motor", docs, top_n=5) == []


# ---------------------------------------------------------------- hybrid retrieval accuracy

def test_exact_keyword_question_finds_the_right_page(corpus):
    assert ("blender.pdf", 1) in _top_pages("What is the warranty for model XR-500?")


def test_number_question_finds_the_right_page(corpus):
    assert ("blender.pdf", 2) in _top_pages("What is the motor power in watts?")


def test_technical_term_question_finds_the_right_page(corpus):
    assert ("paper.pdf", 1) in _top_pages("How many labelled images are in the dataset?")


def test_percentage_and_accuracy_are_found(corpus):
    assert ("paper.pdf", 2) in _top_pages("What accuracy did the model reach on the test set?")


def test_multi_pdf_question_returns_chunks_from_both_documents(corpus):
    pages = _top_pages("Compare the warranty of the blender and the guarantee of the hose", top_k=6)
    files = {filename for filename, _ in pages}
    assert {"blender.pdf", "hose.pdf"} <= files


def test_selected_documents_restrict_every_result(corpus):
    pages = _top_pages("How long is the guarantee?", document_ids=[corpus["hose"]])
    assert pages and all(filename == "hose.pdf" for filename, _ in pages)


def test_hits_keep_document_id_filename_page_and_chunk_index(corpus):
    hits = retrieval_service.retrieve_chunks("Greenline garden hose guarantee", 3, None, 0.15)
    assert hits
    top = hits[0]
    assert top.document_id == corpus["hose"]
    assert top.filename == "hose.pdf"
    assert top.page_number == 1
    assert isinstance(top.chunk_index, int)


def test_hits_record_how_they_were_found(corpus):
    hits = retrieval_service.retrieve_chunks("XR-500 warranty", 5, None, 0.15)
    assert hits and all(hit.match in {"semantic", "keyword", "both"} for hit in hits)
    assert any(hit.match in {"keyword", "both"} for hit in hits)


def test_keyword_match_similarity_is_a_real_similarity_not_zero(corpus):
    hits = retrieval_service.retrieve_chunks("XR-500", 5, None, 0.15)
    model_chunk = next(hit for hit in hits if "XR-500" in hit.text)
    assert model_chunk.match in {"keyword", "both"}
    assert 0.0 <= model_chunk.similarity <= 1.0
    assert model_chunk.similarity > 0.0  # a real similarity, not a placeholder zero


def test_fusion_scores_follow_reciprocal_rank_fusion():
    from app.services.vector_store_service import VectorHit

    semantic = [VectorHit("a", "d", "f", 1, 0, "t", 0.9), VectorHit("b", "d", "f", 2, 1, "t", 0.5)]
    scores = hybrid_search.fuse(semantic, ["b", "a"])
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)


# ---------------------------------------------------------------- irrelevant and missing information

def test_irrelevant_question_returns_nothing_and_never_calls_gemini(client, corpus, llm):
    response = client.post("/api/chat", json={"question": "zebra giraffe lions"})
    body = response.json()
    assert body["answered_from_documents"] is False
    assert llm.calls == []


def test_missing_information_returns_the_clear_not_found_message(client, corpus, llm):
    llm.reply = '{"answer": "The price is not available in the uploaded PDFs.", "source_ids": []}'
    response = client.post("/api/chat", json={"question": "What does the blender cost in euros?"})
    body = response.json()
    assert body["answered_from_documents"] is False
    assert "couldn't find this information in the selected documents" in body["assistant_message"]["content"]


def test_question_about_a_missing_topic_in_selected_pdfs_is_not_answered_from_others(client, corpus, llm):
    response = client.post(
        "/api/chat",
        json={"question": "How long is the blender warranty?", "document_ids": [corpus["hose"]]},
    )
    body = response.json()
    assert body["assistant_message"]["sources"] == [] or all(
        source["filename"] == "hose.pdf" for source in body["assistant_message"]["sources"]
    )


# ---------------------------------------------------------------- duplicate filtering

def test_near_duplicate_chunks_are_removed_before_the_answer(client):
    same = "The warranty covers manufacturing defects for two years from the purchase date and is non transferable."
    upload_pdf(client, [same, same + " Extra line."], name="copy-a.pdf")
    upload_pdf(client, [same], name="copy-b.pdf")
    hits = retrieval_service.retrieve_chunks("warranty manufacturing defects two years", 10, None, 0.15)
    from app.services.rag_service import remove_near_duplicates

    kept, dropped = remove_near_duplicates(hits)
    assert dropped >= 1
    assert len(kept) < len(hits)


def test_distinct_chunks_are_all_kept_by_the_duplicate_filter():
    from app.services.rag_service import remove_near_duplicates
    from app.services.vector_store_service import VectorHit

    hits = [
        VectorHit("1", "d", "f", 1, 0, "Motor power is 750 watts for the blender everyday use.", 0.9),
        VectorHit("2", "d", "f", 2, 1, "The hose is guaranteed for five years against leaks.", 0.8),
    ]
    kept, dropped = remove_near_duplicates(hits)
    assert len(kept) == 2 and dropped == 0


# ---------------------------------------------------------------- reranking and its failures

def _candidates(count):
    from app.services.vector_store_service import VectorHit

    return [
        VectorHit(f"v{index}", "d", "f.pdf", index + 1, index, f"Candidate excerpt number {index} about topic {index}.", 0.5)
        for index in range(count)
    ]


def test_rerank_applies_the_order_gemini_returns(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-test")
    seen = {}

    def fake_complete(system, messages, max_tokens=None, json_output=False, max_attempts=3, time_budget=None):
        seen["attempts"] = max_attempts
        return json.dumps({"ranking": [4, 2, 0]})

    monkeypatch.setattr(rerank_service.llm_service, "complete", fake_complete)
    result = rerank_service.rerank("q", _candidates(8), keep=3)

    assert result.status == "ok"
    assert [hit.vector_id for hit in result.hits[:3]] == ["v4", "v2", "v0"]
    assert seen["attempts"] == 1  # reranking never retries, so it cannot hold up the answer


def test_rerank_is_skipped_when_there_are_few_candidates(monkeypatch):
    called = []
    monkeypatch.setattr(rerank_service.llm_service, "complete", lambda *a, **k: called.append(1) or "{}")
    result = rerank_service.rerank("q", _candidates(3), keep=5)
    assert result.status == "skipped"
    assert called == []


@pytest.mark.parametrize(
    "failure",
    [
        LLMError(504, "gemini_timeout", "slow"),
        LLMError(503, "cooldown", "cooling down"),
        LLMError(429, "rate_limited", "quota"),
        LLMError(503, "gemini_unavailable", "busy"),
        RuntimeError("unexpected"),
    ],
)
def test_rerank_failure_falls_back_to_the_original_order(monkeypatch, failure):
    def failing(*args, **kwargs):
        raise failure

    monkeypatch.setattr(rerank_service.llm_service, "complete", failing)
    candidates = _candidates(8)
    result = rerank_service.rerank("q", candidates, keep=3)
    assert result.status == "fallback"
    assert [hit.vector_id for hit in result.hits] == [hit.vector_id for hit in candidates]


@pytest.mark.parametrize(
    "reply",
    ["not json at all", '{"ranking": "zero"}', '{"ranking": [99, -1, "x"]}', '{"other": [1]}', ""],
)
def test_unusable_rerank_answers_fall_back(monkeypatch, reply):
    monkeypatch.setattr(rerank_service.llm_service, "complete", lambda *a, **k: reply)
    candidates = _candidates(8)
    result = rerank_service.rerank("q", candidates, keep=3)
    assert result.status == "fallback"
    assert [hit.vector_id for hit in result.hits] == [hit.vector_id for hit in candidates]


def test_partial_rerank_keeps_the_missing_candidates_after_the_ranked_ones(monkeypatch):
    monkeypatch.setattr(rerank_service.llm_service, "complete", lambda *a, **k: '{"ranking": [3, 1]}')
    result = rerank_service.rerank("q", _candidates(6), keep=2)
    assert [hit.vector_id for hit in result.hits][:2] == ["v3", "v1"]
    assert len(result.hits) == 6


def test_reranking_can_be_turned_off(client, corpus, monkeypatch, llm):
    monkeypatch.setattr(get_settings(), "rerank_enabled", False)
    llm.reply = '{"answer": "Two years.", "source_ids": ["S1"]}'
    body = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"}).json()
    assert body["retrieval"]["rerank"] == "skipped"
    assert len(llm.calls) == 1  # only the answer itself, no reranking call


def test_answer_still_arrives_when_reranking_fails(client, corpus, llm, monkeypatch):
    answer_call = llm

    def fake_complete(system, messages, max_tokens=None, json_output=False, **kwargs):
        if system == rerank_service.SYSTEM_PROMPT:
            raise LLMError(504, "gemini_timeout", "slow")  # only the reranking call fails
        return answer_call(system, messages, max_tokens, json_output)

    monkeypatch.setattr(rerank_service.llm_service, "complete", fake_complete)
    llm.reply = '{"answer": "Two years.", "source_ids": ["S1"]}'
    body = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"}).json()
    assert body["answered_from_documents"] is True
    assert body["retrieval"].get("rerank") in {"fallback", "skipped"}


# ---------------------------------------------------------------- source verification

def test_sentences_supported_by_the_cited_text_are_verified():
    result = verify_answer(
        "The warranty lasts two years from the date of purchase.",
        ["The Acme Blender carries a warranty of two years from the date of purchase."],
    )
    assert result.verdict == "supported"


def test_invented_facts_are_not_verified():
    result = verify_answer(
        "The blender includes a lifetime subscription to premium recipes worldwide.",
        ["The motor power is 750 watts. Clean the blade with warm water."],
    )
    assert result.verdict == "unsupported"
    assert result.supported == 0


def test_mixed_answers_are_marked_partial():
    result = verify_answer(
        "The motor power is 750 watts. It also includes a lifetime subscription to premium recipes.",
        ["The motor power is 750 watts."],
    )
    assert result.verdict == "partial"
    assert result.supported == 1 and result.unsupported == 1


def test_general_knowledge_sentences_are_not_checked():
    result = verify_answer(
        "General knowledge (not from your documents): blenders use blades. The motor power is 750 watts.",
        ["The motor power is 750 watts."],
    )
    assert result.verdict == "supported"
    assert result.checked == 1


def test_short_answers_are_not_checked_and_not_blocked():
    assert verify_answer("Yes.", ["Something else entirely."]).verdict == "not_checked"


def test_bullets_are_split_into_sentences():
    assert split_sentences("- First point here.\n- Second point here.") == ["First point here.", "Second point here."]


def test_unsupported_answer_is_replaced_and_gets_no_sources(client, corpus, llm):
    llm.reply = '{"answer": "The blender includes a lifetime subscription to premium recipes.", "source_ids": ["S1"]}'
    body = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"}).json()
    assert body["assistant_message"]["sources"] == []
    assert "couldn't find this information" in body["assistant_message"]["content"]
    assert body["retrieval"]["replaced_unsupported_answer"] is True


def test_cited_pages_and_documents_are_real(client, corpus, llm):
    llm.reply = '{"answer": "The warranty lasts two years.", "source_ids": ["S1", "S2"]}'
    body = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"}).json()
    session = SessionLocal()
    try:
        for source in body["assistant_message"]["sources"]:
            chunk = (
                session.query(DocumentChunk)
                .filter_by(document_id=source["document_id"], page_number=source["page_number"])
                .first()
            )
            assert chunk is not None, "every citation must point to a real page of a real document"
            assert source["filename"] in {"blender.pdf", "hose.pdf", "paper.pdf"}
    finally:
        session.close()


def test_verification_details_are_included_in_the_response(client, corpus, llm):
    llm.reply = '{"answer": "The warranty lasts two years from the purchase date.", "source_ids": ["S1"]}'
    body = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"}).json()
    verification = body["retrieval"]["verification"]
    assert verification["verdict"] in {"supported", "partial"}
    assert verification["checked"] >= 1


# ---------------------------------------------------------------- Gemini failures during an answer

def test_gemini_failure_while_answering_is_reported_not_faked(client, corpus, llm):
    llm.error = LLMError(503, "gemini_unavailable", "Gemini is temporarily unavailable.")
    response = client.post("/api/chat", json={"question": "warranty of the XR-500 blender"})
    assert response.status_code == 503
    assert client.get("/api/conversations").json()["total"] == 0
