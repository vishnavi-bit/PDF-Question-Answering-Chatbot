"""Quiz scoring, saved attempts, progress, weak topics and flashcard tracking."""

from __future__ import annotations

import json

from tests.helpers import upload_pdf

PAGE = "Warranty covers motor defects for two years. Cleaning: wash the jar with warm water."


def _quiz_payload(correct_indexes, topics):
    return {
        "questions": [
            {
                "question": f"Question {number}?",
                "options": ["A", "B", "C", "D"],
                "correct_index": correct,
                "explanation": "Explanation text.",
                "topic": topics[number],
                "source_ids": ["S1"],
            }
            for number, correct in enumerate(correct_indexes)
        ]
    }


def _make_quiz(client, llm, correct_indexes, topics):
    document = upload_pdf(client, [PAGE], name="study.pdf").json()["document"]
    llm.reply = json.dumps(_quiz_payload(correct_indexes, topics))
    response = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- grading

def test_quiz_score_and_percentage_are_calculated_by_the_server(client, llm):
    quiz = _make_quiz(client, llm, [0, 1, 2, 3], ["Warranty", "Warranty", "Cleaning", "Cleaning"])

    result = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0, 1, 0, None]}).json()

    assert result["total"] == 4
    assert result["correct"] == 2
    assert result["percent"] == 50.0
    assert [item["is_correct"] for item in result["items"]] == [True, True, False, False]
    assert result["items"][2]["correct_index"] == 2
    assert result["items"][0]["explanation"] == "Explanation text."


def test_correct_answers_are_hidden_until_grading(client, llm):
    quiz = _make_quiz(client, llm, [0, 1], ["Warranty", "Cleaning"])

    public = client.get(f"/api/study/quizzes/{quiz['id']}").json()

    serialised = json.dumps(public)
    assert "correct_index" not in serialised
    assert "explanation" not in serialised


def test_wrong_number_of_answers_is_rejected(client, llm):
    quiz = _make_quiz(client, llm, [0, 1, 2], ["Warranty", "Warranty", "Warranty"])

    response = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0]})

    assert response.status_code == 422
    assert "3 questions" in response.json()["detail"]


def test_invalid_option_number_is_rejected(client, llm):
    quiz = _make_quiz(client, llm, [0], ["Warranty"])
    response = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [7]})
    assert response.status_code == 422


def test_grading_an_unknown_quiz_returns_404(client):
    response = client.post("/api/study/quizzes/9999/attempts", json={"answers": [0]})
    assert response.status_code == 404


def test_grading_saves_an_attempt_that_survives_a_reload(client, llm):
    quiz = _make_quiz(client, llm, [0, 0], ["Warranty", "Warranty"])
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0, 3]})

    progress = client.get("/api/study/progress").json()

    assert progress["total_attempts"] == 1
    assert progress["attempts"][0]["correct"] == 1
    assert progress["attempts"][0]["quiz_title"].startswith("Quiz (2 questions)")


# ---------------------------------------------------------------- progress and weak topics

def test_progress_shows_accuracy_and_topic_breakdown_across_attempts(client, llm):
    quiz = _make_quiz(client, llm, [0, 0, 0, 0], ["Warranty", "Warranty", "Cleaning", "Cleaning"])
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0, 0, 3, 3]})  # 2/4
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0, 0, 0, 0]})  # 4/4

    progress = client.get("/api/study/progress").json()

    assert progress["total_attempts"] == 2
    assert progress["questions_answered"] == 8
    assert progress["overall_accuracy"] == 75.0
    topics = {topic["topic"]: topic for topic in progress["topics"]}
    assert topics["Warranty"]["accuracy"] == 100.0
    assert topics["Cleaning"]["attempted"] == 4
    assert topics["Cleaning"]["correct"] == 2


def test_weak_topics_are_those_below_sixty_percent(client, llm):
    quiz = _make_quiz(client, llm, [0, 0, 0, 0], ["Warranty", "Warranty", "Cleaning", "Cleaning"])
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0, 0, 1, 2]})  # Warranty 100%, Cleaning 0%

    progress = client.get("/api/study/progress").json()

    weak = [topic["topic"] for topic in progress["weak_topics"]]
    assert weak == ["Cleaning"]


def test_progress_with_no_attempts_has_no_accuracy_yet(client):
    progress = client.get("/api/study/progress").json()
    assert progress["total_attempts"] == 0
    assert progress["overall_accuracy"] is None
    assert progress["weak_topics"] == []


def test_deleting_a_pdf_keeps_saved_attempts(client, llm):
    document = upload_pdf(client, [PAGE], name="temp.pdf").json()["document"]
    llm.reply = json.dumps(_quiz_payload([0], ["Warranty"]))
    quiz = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [document["id"]]}).json()
    client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [0]})

    client.delete(f"/api/documents/{document['id']}")

    assert client.get("/api/study/progress").json()["total_attempts"] == 1


# ---------------------------------------------------------------- flashcards

def _make_deck(client, llm, count=3):
    document = upload_pdf(client, [PAGE], name="cards.pdf").json()["document"]
    llm.reply = json.dumps({"cards": [
        {"question": f"Card {i}?", "answer": f"Answer {i}.", "source_ids": ["S1"]} for i in range(count)
    ]})
    return client.post("/api/study/flashcards", json={"count": 5, "document_ids": [document["id"]]}).json()


def test_flashcards_can_be_marked_studied_and_unmarked(client, llm):
    deck = _make_deck(client, llm)

    studied = client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 1, "studied": True}).json()
    assert studied["studied_indices"] == [1]

    studied = client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 1, "studied": False}).json()
    assert studied["studied_indices"] == []


def test_marking_the_same_card_twice_is_harmless(client, llm):
    deck = _make_deck(client, llm)
    client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 0, "studied": True})
    result = client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 0, "studied": True}).json()
    assert result["studied_indices"] == [0]


def test_flashcard_progress_appears_in_the_overview(client, llm):
    deck = _make_deck(client, llm, count=4)
    client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 0, "studied": True})
    client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 2, "studied": True})

    decks = client.get("/api/study/progress").json()["flashcard_decks"]

    assert decks[0]["id"] == deck["id"]
    assert decks[0]["total"] == 4
    assert decks[0]["studied"] == 2


def test_flashcard_index_outside_the_deck_is_rejected(client, llm):
    deck = _make_deck(client, llm, count=2)
    response = client.put(f"/api/study/flashcards/{deck['id']}/progress", json={"card_index": 9, "studied": True})
    assert response.status_code == 422


def test_quiz_id_cannot_be_used_as_a_flashcard_deck(client, llm):
    quiz = _make_quiz(client, llm, [0], ["Warranty"])
    response = client.get(f"/api/study/flashcards/{quiz['id']}")
    assert response.status_code == 404
