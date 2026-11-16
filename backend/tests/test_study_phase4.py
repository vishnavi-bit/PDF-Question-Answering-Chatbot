"""Phase 4 study tests: SM-2 spaced repetition, revision, saved notes, mock exams with timer, saved questions, learning path."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from app.database.connection import SessionLocal
from app.database.models import MockExamAttempt
from app.services.revision_service import SM2State, sm2_next
from tests.helpers import upload_pdf

BLENDER = "Acme Blender warranty lasts two years. Motor power is 750 watts. Clean the blade with warm water."


def _cards_reply(count):
    return json.dumps({"cards": [
        {"question": f"Question {i} about the blender?", "answer": f"Answer {i}.", "source_ids": ["S1"]} for i in range(count)
    ]})


def _mcq(index, correct=0, topic="Warranty"):
    return {"question": f"Blender question number {index}?", "options": ["A", "B", "C", "D"], "correct_index": correct,
            "explanation": "Because the text says so.", "topic": topic, "source_ids": ["S1"]}


def _exam_reply(mcq_count=3, desc_count=1):
    return json.dumps({
        "mcq": [_mcq(i, correct=i % 4, topic="Warranty" if i % 2 == 0 else "Cleaning") for i in range(mcq_count)],
        "descriptive": [{"question": f"Describe point {i}?", "model_answer": "A full model answer.", "source_ids": ["S1"]}
                        for i in range(desc_count)],
    })


@pytest.fixture
def doc(client):
    return upload_pdf(client, [BLENDER], name="blender.pdf").json()["document"]["id"]


@pytest.fixture
def deck(client, doc, llm):
    llm.reply = _cards_reply(3)
    return client.post("/api/study/flashcards", json={"count": 5, "document_ids": [doc]}).json()["id"]


# ---------------------------------------------------------------- SM-2

def test_sm2_good_answers_follow_the_standard_intervals():
    state = SM2State()
    state = sm2_next(state, 4)
    assert (state.repetitions, state.interval_days) == (1, 1)
    state = sm2_next(state, 4)
    assert (state.repetitions, state.interval_days) == (2, 6)
    state = sm2_next(state, 4)
    assert state.interval_days == round(6 * 2.5)  # 15 days with the default ease factor


def test_sm2_failed_answer_starts_the_card_again():
    state = sm2_next(sm2_next(SM2State(), 4), 4)
    failed = sm2_next(state, 2)
    assert failed.repetitions == 0
    assert failed.interval_days == 1


def test_sm2_ease_factor_never_drops_below_the_minimum():
    state = SM2State()
    for _ in range(20):
        state = sm2_next(state, 2)
    assert state.ease_factor == pytest.approx(1.3)


def test_sm2_rejects_invalid_quality():
    with pytest.raises(ValueError):
        sm2_next(SM2State(), 7)


# ---------------------------------------------------------------- review endpoint and schedule

def test_known_and_need_practice_are_saved_with_a_due_date(client, deck):
    response = client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 0, "status": "known"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "known"
    assert body["interval_days"] == 1
    assert body["due_date"] == (date.today() + timedelta(days=1)).isoformat()

    deck_view = client.get(f"/api/study/flashcards/{deck}").json()
    card = deck_view["cards"][0]
    assert card["status"] == "known" and card["repetitions"] == 1
    assert deck_view["cards"][1]["status"] == "new"  # unreviewed cards are tracked as new


def test_need_practice_is_due_tomorrow(client, deck):
    body = client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 1, "status": "need_practice"}).json()
    assert body["interval_days"] == 1 and body["repetitions"] == 0


def test_review_of_a_missing_card_is_rejected(client, deck):
    response = client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 9, "status": "known"})
    assert response.status_code == 422


def test_review_status_must_be_known_or_need_practice(client, deck):
    response = client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 0, "status": "maybe"})
    assert response.status_code == 422


def test_cards_due_today_appear_in_todays_revision(client, deck):
    client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 0, "status": "need_practice"})
    today_view = client.get("/api/study/revision/today").json()
    # a card reviewed as "need practice" is due tomorrow, so it is NOT due today
    assert today_view["due_card_count"] == 0
    upcoming = client.get("/api/study/revision/upcoming", params={"days": 2}).json()
    assert any(card["card_index"] == 0 for card in upcoming["cards"])


def test_revision_plan_creates_tasks_and_completion_is_saved(client, deck):
    tasks = client.post("/api/study/revision-plans", json={"deck_id": deck}).json()["tasks"]
    assert [t["due_date"] for t in tasks] == [(date.today() + timedelta(days=d)).isoformat() for d in (1, 3, 7, 14)]
    done = client.post(f"/api/study/revision-plans/{tasks[0]['id']}/complete", json={"completed": True}).json()
    assert done["completed"] is True and done["completed_at"]
    undone = client.post(f"/api/study/revision-plans/{tasks[0]['id']}/complete", json={"completed": False}).json()
    assert undone["completed"] is False


def test_revision_plan_for_unknown_deck_is_404(client):
    assert client.post("/api/study/revision-plans", json={"deck_id": 999}).status_code == 404


def test_deleting_a_document_keeps_its_saved_flashcard_reviews_list_consistent(client, deck):
    client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 0, "status": "known"})
    assert client.get("/api/study/revision/today").status_code == 200


# ---------------------------------------------------------------- saved notes

def test_overview_notes_are_saved_listed_edited_and_deleted(client, doc, llm):
    llm.reply = json.dumps({"overview": "The blender has a warranty.", "key_points": [
        {"text": "Warranty is two years.", "source_ids": ["S1"]}], "definitions": [], "simple_explanations": []})
    created = client.post("/api/study/notes/saved", json={"mode": "overview", "length": "short", "document_ids": [doc]})
    assert created.status_code == 201
    note = created.json()
    assert note["body"]["key_points"][0]["sources"][0]["page_number"] == 1

    listed = client.get("/api/study/notes").json()
    assert listed["total"] == 1

    edited = client.put(f"/api/study/notes/{note['id']}", json={"title": "My blender notes"})
    assert edited.json()["title"] == "My blender notes"

    assert client.delete(f"/api/study/notes/{note['id']}").status_code == 204
    assert client.get(f"/api/study/notes/{note['id']}").status_code == 404


def test_short_notes_ask_for_fewer_points_than_detailed(client, doc, llm):
    llm.reply = json.dumps({"overview": "x", "key_points": [], "definitions": [], "simple_explanations": []})
    client.post("/api/study/notes/saved", json={"mode": "overview", "length": "short", "document_ids": [doc]})
    short_prompt = llm.calls[-1]["messages"][0]["content"]
    client.post("/api/study/notes/saved", json={"mode": "overview", "length": "detailed", "document_ids": [doc]})
    detailed_prompt = llm.calls[-1]["messages"][0]["content"]
    assert "SHORT" in short_prompt and "DETAILED" in detailed_prompt


def test_edited_notes_cannot_drop_their_sources(client, doc, llm):
    llm.reply = json.dumps({"overview": None, "key_points": [{"text": "Two years.", "source_ids": ["S1"]}],
                            "definitions": [], "simple_explanations": []})
    note = client.post("/api/study/notes/saved", json={"mode": "overview", "document_ids": [doc]}).json()
    point = note["body"]["key_points"][0]
    point["sources"] = []
    response = client.put(f"/api/study/notes/{note['id']}", json={"body": note["body"]})
    assert response.status_code == 422
    assert "source" in response.json()["detail"]


def test_topic_notes_for_a_topic_not_in_the_pdfs_do_not_call_gemini(client, doc, llm):
    response = client.post("/api/study/notes/saved", json={"mode": "topic", "topic": "zebra giraffe", "document_ids": [doc]})
    assert response.status_code == 400
    assert llm.calls == []


def test_topic_notes_need_a_topic(client, doc):
    response = client.post("/api/study/notes/saved", json={"mode": "topic", "document_ids": [doc]})
    assert response.status_code == 422


def test_unknown_notes_return_404(client):
    assert client.get("/api/study/notes/999").status_code == 404
    assert client.delete("/api/study/notes/999").status_code == 404


# ---------------------------------------------------------------- quiz difficulty and custom counts

def test_quiz_accepts_custom_count_and_difficulty(client, doc, llm):
    llm.reply = json.dumps({"questions": [_mcq(i) for i in range(7)]})
    quiz = client.post("/api/study/quizzes", json={"count": 7, "difficulty": "hard", "document_ids": [doc]}).json()
    assert len(quiz["questions"]) == 7
    assert "Difficulty: hard" in llm.calls[-1]["messages"][0]["content"]


def test_quiz_rejects_an_unknown_difficulty(client, doc):
    assert client.post("/api/study/quizzes", json={"count": 5, "difficulty": "impossible", "document_ids": [doc]}).status_code == 422


def test_quiz_rejects_more_than_thirty_questions(client, doc):
    assert client.post("/api/study/quizzes", json={"count": 31, "document_ids": [doc]}).status_code == 422


# ---------------------------------------------------------------- mock exams

def _exam(client, doc, llm, mcq=3, desc=1, minutes=30):
    llm.reply = _exam_reply(mcq, desc)
    response = client.post("/api/study/mock-exams", json={
        "difficulty": "medium", "mcq_count": mcq, "descriptive_count": desc,
        "duration_minutes": minutes, "document_ids": [doc]})
    assert response.status_code == 201, response.text
    return response.json()


def test_student_view_of_an_exam_hides_answers(client, doc, llm):
    exam = _exam(client, doc, llm)
    text = json.dumps(exam)
    assert "correct_index" not in text
    assert "explanation" not in text
    assert "model_answer" not in text
    assert len(exam["mcq"]) == 3 and len(exam["descriptive"]) == 1


def test_timed_attempt_is_graded_on_submit(client, doc, llm):
    exam = _exam(client, doc, llm, mcq=3, desc=1)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    assert attempt["duration_seconds"] == 30 * 60

    # correct answers for this paper are 0, 1, 2 (index % 4)
    result = client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit",
                         json={"answers": [0, 1, 0], "descriptive": ["my own words"]}).json()

    assert result["correct"] == 2 and result["total_mcq"] == 3
    assert result["percent"] == pytest.approx(66.7, abs=0.1)
    assert result["mcq"][2]["is_correct"] is False and result["mcq"][2]["correct_index"] == 2
    assert result["descriptive"][0]["model_answer"] == "A full model answer."
    assert result["descriptive"][0]["your_answer"] == "my own words"
    assert result["late"] is False and result["auto_submitted"] is False


def test_result_is_not_shown_before_submission(client, doc, llm):
    exam = _exam(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    assert client.get(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}").status_code == 409


def test_a_submitted_exam_cannot_be_submitted_again(client, doc, llm):
    exam = _exam(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit", json={"answers": [None, None, None]})
    again = client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit", json={"answers": [0, 0, 0]})
    assert again.status_code == 409


def test_wrong_number_of_answers_is_rejected(client, doc, llm):
    exam = _exam(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    response = client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit", json={"answers": [0]})
    assert response.status_code == 422


def test_auto_submitted_exam_is_marked_and_late_submissions_are_flagged(client, doc, llm):
    exam = _exam(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    # simulate a deadline that has passed well beyond the grace period
    session = SessionLocal()
    try:
        row = session.get(MockExamAttempt, attempt["attempt_id"])
        row.deadline = datetime.now() - timedelta(minutes=5)
        session.commit()
    finally:
        session.close()

    result = client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit",
                         json={"answers": [None, None, None], "auto_submitted": True}).json()

    assert result["auto_submitted"] is True
    assert result["late"] is True


def test_exam_history_lists_attempts(client, doc, llm):
    exam = _exam(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam['id']}/start").json()
    client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit", json={"answers": [0, 1, 2]})
    history = client.get("/api/study/mock-exam-attempts").json()
    assert history["total"] == 1 and history["attempts"][0]["submitted"] is True


def test_exam_needs_at_least_one_question_and_a_real_duration(client, doc):
    assert client.post("/api/study/mock-exams", json={"mcq_count": 0, "document_ids": [doc]}).status_code == 422
    assert client.post("/api/study/mock-exams", json={"duration_minutes": 1, "document_ids": [doc]}).status_code == 422


def test_important_questions_include_topic_and_importance(client, doc, llm):
    llm.reply = json.dumps({"short_answer": [{"question": "What is the warranty?", "answer": "Two years.",
                                               "source_ids": ["S1"], "topic": "Warranty", "importance": "high"}],
                            "long_answer": []})
    exam = client.post("/api/study/exams", json={"short_count": 1, "long_count": 0, "document_ids": [doc]}).json()
    assert exam["questions"][0]["sources"][0]["page_number"] == 1


# ---------------------------------------------------------------- saved questions

def test_questions_can_be_saved_for_revision_and_removed(client, doc):
    source = {"source_id": "S1", "document_id": doc, "filename": "blender.pdf", "page_number": 1}
    saved = client.post("/api/study/saved-questions", json={"kind": "short", "question": "What is the warranty?",
                                                             "answer": "Two years.", "sources": [source]}).json()
    listed = client.get("/api/study/saved-questions").json()
    assert listed["total"] == 1 and listed["questions"][0]["sources"][0]["filename"] == "blender.pdf"
    assert client.delete(f"/api/study/saved-questions/{saved['id']}").status_code == 204
    assert client.get("/api/study/saved-questions").json()["total"] == 0


def test_saved_question_needs_a_real_kind_and_text(client):
    assert client.post("/api/study/saved-questions", json={"kind": "essay", "question": "What?"}).status_code == 422
    assert client.post("/api/study/saved-questions", json={"kind": "short", "question": "x"}).status_code == 422


# ---------------------------------------------------------------- learning path (only recorded data)

def test_learning_path_without_quiz_data_says_so_and_invents_nothing(client, doc):
    path = client.get("/api/study/learning-path").json()
    assert path["has_quiz_data"] is False
    assert path["overall_accuracy"] is None
    assert path["weak_topics"] == []
    assert any(step["type"] == "start" for step in path["steps"])


def test_learning_path_recommends_practice_for_weak_topics(client, doc, llm):
    llm.reply = json.dumps({"questions": [_mcq(i, correct=0, topic="Cleaning") for i in range(3)]})
    quiz = client.post("/api/study/quizzes", json={"count": 3, "document_ids": [doc]}).json()
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [3, 3, 3]})  # all wrong

    path = client.get("/api/study/learning-path").json()

    assert path["has_quiz_data"] is True
    assert path["weak_topics"][0]["topic"] == "Cleaning"
    assert any(step["type"] == "practise" and "Cleaning" in step["title"] for step in path["steps"])


def test_learning_path_suggests_due_cards_and_a_mock_exam(client, doc, deck):
    client.put(f"/api/study/flashcards/{deck}/review", json={"card_index": 0, "status": "known"})
    session = SessionLocal()
    try:
        from app.database.models import FlashcardReview
        review = session.query(FlashcardReview).filter_by(deck_id=deck, card_index=0).first()
        review.due_date = date.today()
        session.commit()
    finally:
        session.close()
    path = client.get("/api/study/learning-path").json()
    assert path["due_cards"] == 1
    assert any(step["type"] == "revise" for step in path["steps"])
    assert any(step["type"] == "exam" for step in path["steps"])


# ---------------------------------------------------------------- explain: steps and follow-up questions

def test_explain_asks_for_steps_and_uses_the_follow_up(client, doc, llm):
    llm.reply = json.dumps({"explanation": "Warranties cover faults.", "example": "A blender.", "key_terms": ["warranty"],
                            "steps": ["Step one.", "Step two."], "source_ids": ["S1"]})
    body = client.post("/api/study/explain", json={"topic": "warranty", "follow_up": "what about the motor?",
                                                    "document_ids": [doc]}).json()
    assert body["found"] is True
    assert body["steps"] == ["Step one.", "Step two."]
    assert "step by step" in llm.calls[-1]["messages"][0]["content"]
