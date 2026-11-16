"""Phase 5 tests: grounded mind maps (saved, renamed, deleted) and ReportLab PDF exports."""

from __future__ import annotations

import json

import pymupdf
import pytest

from app.services import mind_map_service
from tests.helpers import upload_pdf

BLENDER = "Acme Blender warranty lasts two years. Motor power is 750 watts. Clean the blade with warm water."


def _mcq(index, correct=0, topic="Warranty"):
    return {"question": f"Blender question number {index}?", "options": ["A", "B", "C", "D"], "correct_index": correct,
            "explanation": "Because the text says so.", "topic": topic, "source_ids": ["S1"]}


def _pdf_text(content: bytes) -> str:
    assert content[:4] == b"%PDF"
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document)


@pytest.fixture
def doc(client):
    return upload_pdf(client, [BLENDER], name="blender.pdf").json()["document"]["id"]


def _map_reply(extra_ungrounded=True):
    branches = [
        {"label": "Warranty", "source_ids": ["S1"], "children": [
            {"label": "Two years", "source_ids": ["S1"]},
            {"label": "Invented subtopic", "source_ids": ["S99"]},   # not a real excerpt: must be dropped
        ]},
        {"label": "Motor", "source_ids": ["S1"], "children": []},
    ]
    if extra_ungrounded:
        branches.append({"label": "Ungrounded branch", "source_ids": [], "children": [{"label": "child", "source_ids": ["S1"]}]})
    return json.dumps({"branches": branches})


# ---------------------------------------------------------------- mind maps: grounding

def test_build_tree_drops_ungrounded_nodes_and_their_children():
    from app.services.study_context import StudyExcerpt

    excerpts = [StudyExcerpt(source_id="S1", document_id="d1", filename="blender.pdf", page_number=2, text="x")]
    data = {"branches": [
        {"label": "Warranty", "source_ids": ["S1"], "children": [
            {"label": "Real", "source_ids": ["S1"]}, {"label": "Fake", "source_ids": ["S42"]}]},
        {"label": "No source", "source_ids": [], "children": [{"label": "child", "source_ids": ["S1"]}]},
        "not a dict",
    ]}
    tree = mind_map_service.build_tree(data, excerpts, centre="blender.pdf")
    assert [b["label"] for b in tree["branches"]] == ["Warranty"]
    assert [c["label"] for c in tree["branches"][0]["children"]] == ["Real"]
    assert tree["branches"][0]["children"][0]["sources"][0]["page_number"] == 2
    assert mind_map_service.count_nodes(tree) == 2


def test_build_tree_caps_branches_and_children():
    from app.services.study_context import StudyExcerpt

    excerpts = [StudyExcerpt(source_id="S1", document_id="d1", filename="a.pdf", page_number=1, text="x")]
    data = {"branches": [{"label": f"B{i}", "source_ids": ["S1"],
                          "children": [{"label": f"C{j}", "source_ids": ["S1"]} for j in range(20)]} for i in range(30)]}
    tree = mind_map_service.build_tree(data, excerpts, centre="a.pdf")
    assert len(tree["branches"]) == mind_map_service.MAX_BRANCHES
    assert len(tree["branches"][0]["children"]) == mind_map_service.MAX_CHILDREN


def test_mind_map_is_saved_with_only_grounded_nodes(client, doc, llm):
    llm.reply = _map_reply()
    response = client.post("/api/study/mind-maps", json={"document_ids": [doc]})
    assert response.status_code == 201, response.text
    body = response.json()
    labels = [b["label"] for b in body["tree"]["branches"]]
    assert labels == ["Warranty", "Motor"]
    assert [c["label"] for c in body["tree"]["branches"][0]["children"]] == ["Two years"]
    assert body["tree"]["centre"] == "blender.pdf"          # centre comes from the PDF name, not the model
    assert body["node_count"] == 3   # Warranty, Two years, Motor
    assert body["tree"]["branches"][0]["sources"][0]["filename"] == "blender.pdf"


def test_mind_map_with_no_grounded_branch_is_not_saved(client, doc, llm):
    llm.reply = json.dumps({"branches": [{"label": "Nothing real", "source_ids": ["S77"]}]})
    response = client.post("/api/study/mind-maps", json={"document_ids": [doc]})
    assert response.status_code == 502
    assert client.get("/api/study/mind-maps").json()["total"] == 0


def test_mind_map_bad_model_output_is_rejected(client, doc, llm):
    llm.reply = "this is not json"
    assert client.post("/api/study/mind-maps", json={"document_ids": [doc]}).status_code == 502


def test_mind_map_crud(client, doc, llm):
    llm.reply = _map_reply()
    map_id = client.post("/api/study/mind-maps", json={"document_ids": [doc]}).json()["id"]

    listed = client.get("/api/study/mind-maps").json()
    assert listed["total"] == 1 and listed["mind_maps"][0]["id"] == map_id

    renamed = client.put(f"/api/study/mind-maps/{map_id}", json={"title": "Blender revision map"}).json()
    assert renamed["title"] == "Blender revision map"

    assert client.put(f"/api/study/mind-maps/{map_id}", json={"title": "x"}).status_code == 422
    assert client.delete(f"/api/study/mind-maps/{map_id}").status_code == 204
    assert client.get(f"/api/study/mind-maps/{map_id}").status_code == 404
    assert client.delete(f"/api/study/mind-maps/{map_id}").status_code == 404


def test_mind_map_needs_a_real_pdf_selection(client):
    assert client.post("/api/study/mind-maps", json={"document_ids": ["nope"]}).status_code in (404, 422)


# ---------------------------------------------------------------- PDF exports: content and formatting

def test_mind_map_export_contains_the_outline_and_sources(client, doc, llm):
    llm.reply = _map_reply()
    map_id = client.post("/api/study/mind-maps", json={"document_ids": [doc]}).json()["id"]
    response = client.get(f"/api/study/export/mind-map/{map_id}.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    text = _pdf_text(response.content)
    assert "Warranty" in text and "Two years" in text
    assert "Source: blender.pdf, page 1" in text
    assert "Page 1" in text                       # page number footer
    assert "Invented subtopic" not in text


def test_notes_export(client, doc, llm):
    llm.reply = json.dumps({"overview": "The blender has a warranty.", "key_points": [
        {"text": "Warranty is two years.", "source_ids": ["S1"]}], "definitions": [], "simple_explanations": []})
    note_id = client.post("/api/study/notes/saved", json={"mode": "overview", "document_ids": [doc]}).json()["id"]
    response = client.get(f"/api/study/export/notes/{note_id}.pdf")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Warranty is two years." in text
    assert "Source: blender.pdf, page 1" in text


def test_quiz_export_has_answer_key_and_quiz_result_export_marks_answers(client, doc, llm):
    llm.reply = json.dumps({"questions": [_mcq(i, correct=1) for i in range(2)]})
    quiz = client.post("/api/study/quizzes", json={"count": 2, "document_ids": [doc]}).json()

    quiz_pdf = client.get(f"/api/study/export/quiz/{quiz['id']}.pdf")
    assert quiz_pdf.status_code == 200
    assert "(correct)" in _pdf_text(quiz_pdf.content)
    assert "Explanation: Because the text says so." in _pdf_text(quiz_pdf.content)

    attempt = client.post(f"/api/study/quizzes/{quiz['id']}/attempts", json={"answers": [1, 0]}).json()
    result_pdf = client.get(f"/api/study/export/quiz-attempt/{attempt['attempt_id']}.pdf")
    assert result_pdf.status_code == 200
    text = _pdf_text(result_pdf.content)
    assert "Score: 1 of 2" in text
    assert "(your answer)" in text


def test_flashcards_export_shows_review_status(client, doc, llm):
    llm.reply = json.dumps({"cards": [{"question": "Power?", "answer": "750 watts.", "source_ids": ["S1"]}]})
    deck = client.post("/api/study/flashcards", json={"count": 5, "document_ids": [doc]}).json()
    client.put(f"/api/study/flashcards/{deck['id']}/review", json={"card_index": 0, "status": "known"})
    response = client.get(f"/api/study/export/flashcards/{deck['id']}.pdf")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Power?" in text and "750 watts." in text and "Status: known" in text


def test_important_questions_export(client, doc, llm):
    llm.reply = json.dumps({"short_answer": [{"question": "What is the warranty?", "answer": "Two years.",
                                               "source_ids": ["S1"]}], "long_answer": []})
    exam = client.post("/api/study/exams", json={"short_count": 1, "long_count": 0, "document_ids": [doc]}).json()
    response = client.get(f"/api/study/export/exam/{exam['id']}.pdf")
    assert response.status_code == 200
    assert "What is the warranty?" in _pdf_text(response.content)


def test_saved_questions_export(client):
    client.post("/api/study/saved-questions", json={"kind": "short", "question": "Motor power?", "answer": "750 watts.",
                                                     "sources": [{"source_id": "S1", "document_id": "d", "filename": "blender.pdf", "page_number": 1}]})
    response = client.get("/api/study/export/saved-questions.pdf")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Motor power?" in text and "Source: blender.pdf, page 1" in text


def _exam_for_export(client, doc, llm):
    llm.reply = json.dumps({
        "mcq": [_mcq(i, correct=i % 4) for i in range(2)],
        "descriptive": [{"question": "Describe the motor?", "model_answer": "Its power is 750 watts.", "source_ids": ["S1"]}],
    })
    return client.post("/api/study/mock-exams", json={"mcq_count": 2, "descriptive_count": 1, "duration_minutes": 20,
                                                       "document_ids": [doc]}).json()["id"]


def test_mock_exam_paper_export_has_answer_key(client, doc, llm):
    exam_id = _exam_for_export(client, doc, llm)
    response = client.get(f"/api/study/export/mock-exam/{exam_id}.pdf")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Time allowed: 20 minutes" in text
    assert "(correct)" in text
    assert "Model answer: Its power is 750 watts." in text


def test_mock_exam_result_export_needs_a_submitted_attempt(client, doc, llm):
    exam_id = _exam_for_export(client, doc, llm)
    attempt = client.post(f"/api/study/mock-exams/{exam_id}/start").json()
    not_yet = client.get(f"/api/study/export/mock-exam-attempt/{attempt['attempt_id']}.pdf")
    assert not_yet.status_code == 409

    client.post(f"/api/study/mock-exam-attempts/{attempt['attempt_id']}/submit",
                json={"answers": [0, 1], "descriptive": ["The motor is 750 watts."], "auto_submitted": True})
    response = client.get(f"/api/study/export/mock-exam-attempt/{attempt['attempt_id']}.pdf")
    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Score:" in text
    assert "submitted automatically" in text
    assert "The motor is 750 watts." in text


def test_export_of_unknown_item_and_unknown_kind(client):
    assert client.get("/api/study/export/notes/999.pdf").status_code == 404
    assert client.get("/api/study/export/quiz/999.pdf").status_code == 404
    assert client.get("/api/study/export/mind-map/999.pdf").status_code == 404
    assert client.get("/api/study/export/unknown-thing/1.pdf").status_code == 422


def test_text_outside_windows_1252_does_not_break_the_pdf(client, doc, llm):
    llm.reply = _map_reply(extra_ungrounded=False).replace("Motor", "Motor → 中文 power")
    map_id = client.post("/api/study/mind-maps", json={"document_ids": [doc]}).json()["id"]
    response = client.get(f"/api/study/export/mind-map/{map_id}.pdf")
    assert response.status_code == 200
    assert "Motor ? ?? power" in _pdf_text(response.content).replace("\n", " ")
