"""Study Assistant generation: grounding, citations, selection of PDFs, and error handling. Gemini is faked."""

from __future__ import annotations

import json

from app.services import llm_service
from app.services.llm_service import LLMError
from tests.helpers import upload_pdf

WARRANTY_PAGE = "Warranty covers motor defects for two years from the date of purchase. Accidents are not covered."
CLEANING_PAGE = "Cleaning instructions: wash the jar with warm soapy water after each use. Never submerge the motor."
CHAPTER_TEXT = (
    "Chapter 1 Introduction\n"
    "Solar energy is light from the sun that can be turned into electricity by panels.\n"
    "Chapter 2 Methods\n"
    "The methods section explains how panels were measured in the field over one year."
)


def _quiz_question(index: int, sources, correct=0, options=None, topic="Warranty"):
    return {
        "question": f"Question number {index} about the material?",
        "options": options or ["Option A", "Option B", "Option C", "Option D"],
        "correct_index": correct,
        "explanation": "Because the excerpt says so.",
        "topic": topic,
        "source_ids": sources,
    }


def _set_reply(llm, payload):
    llm.reply = json.dumps(payload)


# ---------------------------------------------------------------- quizzes

def test_quiz_has_requested_questions_with_four_options_and_real_citations(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE, CLEANING_PAGE], name="manual.pdf").json()["document"]
    _set_reply(llm, {"questions": [_quiz_question(i, ["S1"] if i % 2 else ["S2"]) for i in range(5)]})

    response = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]})

    assert response.status_code == 201
    quiz = response.json()
    assert len(quiz["questions"]) == 5
    assert all(len(question["options"]) == 4 for question in quiz["questions"])
    # the public quiz must not reveal correct answers or explanations
    assert "correct_index" not in quiz["questions"][0]
    assert "explanation" not in quiz["questions"][0]


def test_quiz_citations_point_to_the_correct_pdf_and_page(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE, CLEANING_PAGE], name="manual.pdf").json()["document"]
    _set_reply(llm, {"questions": [_quiz_question(1, ["S2"])]})

    quiz = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]}).json()
    result = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0]}).json()

    source = result["items"][0]["sources"][0]
    assert source["filename"] == "manual.pdf"
    assert source["document_id"] == document["id"]
    assert source["page_number"] == 2  # S2 is the cleaning page


def test_questions_citing_unknown_sources_are_dropped(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="a.pdf").json()["document"]
    _set_reply(
        llm,
        {"questions": [_quiz_question(1, ["S1"]), _quiz_question(2, ["S99"]), _quiz_question(3, [])]},
    )

    quiz = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]}).json()

    assert len(quiz["questions"]) == 1  # only the question grounded in a real excerpt is kept


def test_questions_with_wrong_option_count_are_dropped(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="a.pdf").json()["document"]
    bad = _quiz_question(1, ["S1"], options=["Only", "Two"])
    good = _quiz_question(2, ["S1"])
    _set_reply(llm, {"questions": [bad, good]})

    quiz = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]}).json()

    assert len(quiz["questions"]) == 1
    assert quiz["questions"][0]["question"] == "Question number 2 about the material?"


def test_quiz_fails_clearly_when_nothing_is_grounded(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="a.pdf").json()["document"]
    _set_reply(llm, {"questions": [_quiz_question(1, ["S42"])]})

    response = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]})

    assert response.status_code == 502
    assert "No grounded quiz questions" in response.json()["detail"]


def test_model_text_cannot_invent_a_filename_in_citations(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="real.pdf").json()["document"]
    question = _quiz_question(1, ["S1"])
    question["explanation"] = "According to fake-book.pdf page 99, this is true."
    _set_reply(llm, {"questions": [question]})

    quiz = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]}).json()
    result = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [None]}).json()

    assert result["items"][0]["sources"][0]["filename"] == "real.pdf"
    assert "fake-book.pdf" not in str(result["items"][0]["sources"])


# ---------------------------------------------------------------- notes

def test_notes_overview_keeps_only_grounded_points(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="notes.pdf").json()["document"]
    _set_reply(
        llm,
        {
            "overview": "The warranty is two years.",
            "key_points": [
                {"text": "Motor defects are covered.", "source_ids": ["S1"]},
                {"text": "Made-up point.", "source_ids": ["S9"]},
            ],
            "definitions": [{"term": "Warranty", "meaning": "A promise to repair.", "source_ids": ["S1"]}],
            "simple_explanations": [{"concept": "Warranty", "explanation": "Like a safety promise.", "source_ids": ["S1"]}],
        },
    )

    notes = client.post("/api/study/notes", json={"mode": "overview", "document_ids": [document["id"]]}).json()

    assert notes["overview"] == "The warranty is two years."
    assert [point["text"] for point in notes["key_points"]] == ["Motor defects are covered."]
    assert notes["key_points"][0]["sources"][0]["page_number"] == 1
    assert notes["definitions"][0]["term"] == "Warranty"
    assert notes["simple_explanations"][0]["concept"] == "Warranty"


def test_chapter_notes_use_detected_headings(client, llm):
    document = upload_pdf(client, [CHAPTER_TEXT], name="science.pdf").json()["document"]
    _set_reply(
        llm,
        {"chapters": [
            {"title": "Chapter 1 Introduction", "summary": "Sun light makes power.", "source_ids": ["S1"]},
            {"title": "Chapter 2 Methods", "summary": "Panels were measured.", "source_ids": ["S2"]},
        ]},
    )

    notes = client.post("/api/study/notes", json={"mode": "chapters", "document_ids": [document["id"]]}).json()

    assert notes["mode"] == "chapters"
    assert [chapter["title"] for chapter in notes["chapters"]] == ["Chapter 1 Introduction", "Chapter 2 Methods"]
    assert notes["chapters"][1]["page_start"] == 1


def test_chapter_mode_without_headings_falls_back_to_overview(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="plain.pdf").json()["document"]
    _set_reply(llm, {"overview": "Overview text.", "key_points": [], "definitions": [], "simple_explanations": []})

    notes = client.post("/api/study/notes", json={"mode": "chapters", "document_ids": [document["id"]]}).json()

    assert notes["mode"] == "overview"
    assert "No chapter headings" in notes["note"]


# ---------------------------------------------------------------- flashcards and exam questions

def test_flashcards_are_grounded_and_limited_to_count(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE, CLEANING_PAGE], name="cards.pdf").json()["document"]
    cards = [{"question": f"Card question {i}?", "answer": "An answer.", "source_ids": ["S1" if i % 2 == 0 else "S2"]} for i in range(12)]
    _set_reply(llm, {"cards": cards})

    deck = client.post("/api/study/flashcards", json={"count": 5, "document_ids": [document["id"]]}).json()

    assert len(deck["cards"]) == 5
    assert deck["cards"][0]["sources"][0]["page_number"] == 1
    assert deck["cards"][1]["sources"][0]["page_number"] == 2


def test_exam_questions_include_short_and_long_with_sources(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="exam.pdf").json()["document"]
    _set_reply(
        llm,
        {
            "short_answer": [{"question": "What is covered?", "answer": "Motor defects.", "source_ids": ["S1"]}],
            "long_answer": [{"question": "Explain the warranty.", "answer": "Two years, for defects.", "source_ids": ["S1"]}],
        },
    )

    exam = client.post(
        "/api/study/exams",
        json={"short_count": 1, "long_count": 1, "document_ids": [document["id"]]},
    ).json()

    kinds = [question["kind"] for question in exam["questions"]]
    assert kinds == ["short", "long"]
    assert all(question["sources"][0]["filename"] == "exam.pdf" for question in exam["questions"])


# ---------------------------------------------------------------- explain a topic

def test_explain_topic_uses_matching_excerpts_and_cites_them(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE, CLEANING_PAGE], name="topic.pdf").json()["document"]
    _set_reply(llm, {"explanation": "A warranty is a promise.", "example": "A new blender is fixed free.", "key_terms": ["warranty"], "source_ids": ["S1"]})

    body = client.post("/api/study/explain", json={"topic": "warranty motor defects", "document_ids": [document["id"]]}).json()

    assert body["found"] is True
    assert body["explanation"] == "A warranty is a promise."
    assert body["sources"][0]["page_number"] == 1


def test_explain_topic_not_in_pdfs_does_not_call_gemini(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="topic.pdf").json()["document"]

    body = client.post("/api/study/explain", json={"topic": "zebra giraffe lions", "document_ids": [document["id"]]}).json()

    assert body["found"] is False
    assert llm.calls == []


def test_explain_topic_without_grounded_sources_is_not_presented_as_an_answer(client, llm):
    document = upload_pdf(client, [WARRANTY_PAGE], name="topic.pdf").json()["document"]
    _set_reply(llm, {"explanation": "Invented.", "source_ids": ["S77"]})

    body = client.post("/api/study/explain", json={"topic": "warranty motor", "document_ids": [document["id"]]}).json()

    assert body["found"] is False
    assert body["explanation"] is None


# ---------------------------------------------------------------- selection of PDFs

def test_only_the_selected_pdf_text_is_sent_to_gemini(client, llm):
    first = upload_pdf(client, [WARRANTY_PAGE], name="warranty.pdf").json()["document"]
    upload_pdf(client, [CLEANING_PAGE], name="cleaning.pdf")
    _set_reply(llm, {"cards": [{"question": "Warranty length?", "answer": "Two years.", "source_ids": ["S1"]}]})

    client.post("/api/study/flashcards", json={"count": 5, "document_ids": [first["id"]]})

    sent = llm.calls[-1]["messages"][0]["content"]
    assert "warranty.pdf" in sent
    assert "cleaning.pdf" not in sent
    assert "wash the jar" not in sent


def test_several_selected_pdfs_share_the_context(client, llm):
    first = upload_pdf(client, [WARRANTY_PAGE], name="warranty.pdf").json()["document"]
    second = upload_pdf(client, [CLEANING_PAGE], name="cleaning.pdf").json()["document"]
    _set_reply(llm, {"cards": [{"question": "Q?", "answer": "A.", "source_ids": ["S1"]}]})

    client.post("/api/study/flashcards", json={"count": 5, "document_ids": [first["id"], second["id"]]})

    sent = llm.calls[-1]["messages"][0]["content"]
    assert "warranty.pdf" in sent and "cleaning.pdf" in sent


def test_unknown_selected_pdf_is_rejected(client, llm):
    upload_pdf(client, [WARRANTY_PAGE], name="a.pdf")
    response = client.post("/api/study/notes", json={"document_ids": ["does-not-exist"]})
    assert response.status_code == 404
    assert llm.calls == []


def test_study_without_any_ready_pdf_explains_what_to_do(client, llm):
    response = client.post("/api/study/notes", json={"document_ids": []})
    assert response.status_code == 400
    assert "Upload a PDF" in response.json()["detail"]


# ---------------------------------------------------------------- errors

def test_unreadable_ai_answer_is_a_clear_502(client, llm):
    upload_pdf(client, [WARRANTY_PAGE], name="a.pdf")
    llm.reply = "Sorry, I cannot produce JSON right now."

    response = client.post("/api/study/notes", json={"document_ids": []})

    assert response.status_code == 502
    assert response.json()["detail"].startswith("The AI answer could not be read")


def test_rate_limit_error_is_passed_through(client, llm):
    upload_pdf(client, [WARRANTY_PAGE], name="a.pdf")
    llm.error = LLMError(429, "rate_limited", "The Gemini free-tier rate limit or daily quota was reached.")

    response = client.post("/api/study/notes", json={"document_ids": []})

    assert response.status_code == 429


def test_timeout_is_passed_through_as_504(client, llm):
    upload_pdf(client, [WARRANTY_PAGE], name="a.pdf")
    llm.error = LLMError(504, "gemini_timeout", "Gemini did not finish the answer in time.")

    response = client.post("/api/study/quizzes", json={"count": 5, "document_ids": []})

    assert response.status_code == 504


def test_missing_api_key_is_a_clear_503(client, monkeypatch):
    from app.core.config import get_settings

    upload_pdf(client, [WARRANTY_PAGE], name="a.pdf")
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(llm_service, "_client", None)

    response = client.post("/api/study/notes", json={"document_ids": []})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
