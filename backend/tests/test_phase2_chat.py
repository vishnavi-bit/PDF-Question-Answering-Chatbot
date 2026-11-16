"""Phase 2 chat backend: regenerate (replace the last answer safely) and conversation search."""

from __future__ import annotations

import json

import pytest

from app.database.connection import SessionLocal
from app.database.models import Conversation, Message
from app.services import llm_service
from app.services.llm_service import LLMError
from tests.helpers import upload_pdf

WARRANTY = "The warranty lasts two years from the date of purchase and covers motor defects."


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        name, data = "", {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if name:
            out.append((name, data))
    return out


@pytest.fixture
def streamed(monkeypatch):
    """Fake streamed Gemini answers. Set state['text'] to the answer, or state['error'] to fail before text."""
    state = {"text": "Two years.\nSOURCES: S1", "error": None, "calls": 0}

    def fake_stream(system, messages, max_tokens=None, json_output=False):
        state["calls"] += 1
        if state["error"] is not None:
            raise state["error"]
        yield state["text"]

    monkeypatch.setattr(llm_service, "stream_text", fake_stream)
    return state


def _first_exchange(client, streamed, question="How long is the warranty?"):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    streamed["text"] = "Two years from purchase.\nSOURCES: S1"
    response = client.post("/api/chat/stream", json={"question": question})
    events = _events(response.text)
    return events[-1][1]["conversation_id"]


def _messages(conversation_id):
    session = SessionLocal()
    try:
        return [(m.role, m.content) for m in session.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.id)]
    finally:
        session.close()


# ---------------------------------------------------------------- regenerate

def test_regenerate_replaces_the_last_answer_and_keeps_one_question(client, streamed):
    conversation_id = _first_exchange(client, streamed)
    streamed["text"] = "The warranty is two years and covers motor defects.\nSOURCES: S1"

    response = client.post("/api/chat/regenerate", json={"conversation_id": conversation_id})

    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1][0] == "done"
    assert events[-1][1]["assistant_message"]["content"].startswith("The warranty is two years")
    messages = _messages(conversation_id)
    assert [role for role, _ in messages] == ["user", "assistant"]  # no duplicate question, one answer
    assert messages[1][1].startswith("The warranty is two years")


def test_failed_regenerate_keeps_the_original_answer(client, streamed):
    conversation_id = _first_exchange(client, streamed)
    streamed["error"] = LLMError(504, "gemini_timeout", "Gemini did not finish the answer in time.")

    response = client.post("/api/chat/regenerate", json={"conversation_id": conversation_id})

    assert response.status_code == 504
    assert _messages(conversation_id)[1][1] == "Two years from purchase."


def test_regenerate_uses_the_earlier_conversation_as_context(client, streamed, monkeypatch):
    conversation_id = _first_exchange(client, streamed)
    seen = {}

    def spy(system, messages, max_tokens=None, json_output=False):
        seen["messages"] = messages
        yield "Again: two years.\nSOURCES: S1"

    monkeypatch.setattr(llm_service, "stream_text", spy)
    client.post("/api/chat/regenerate", json={"conversation_id": conversation_id})

    assert seen["messages"][-1]["content"].endswith("Question: How long is the warranty?")


def test_regenerate_unknown_conversation_is_404(client, streamed):
    response = client.post("/api/chat/regenerate", json={"conversation_id": 9999})
    assert response.status_code == 404
    assert streamed["calls"] == 0


def test_regenerate_without_any_question_is_a_clear_400(client, streamed):
    session = SessionLocal()
    try:
        conversation = Conversation(title="Empty")
        session.add(conversation)
        session.commit()
        conversation_id = conversation.id
    finally:
        session.close()

    response = client.post("/api/chat/regenerate", json={"conversation_id": conversation_id})

    assert response.status_code == 400
    assert "no question" in response.json()["detail"]


def test_regenerate_uses_the_selected_pdfs(client, streamed):
    first = upload_pdf(client, [WARRANTY], name="policy.pdf").json()["document"]
    upload_pdf(client, ["Clean the jar with warm water."], name="cleaning.pdf")
    streamed["text"] = "Two years.\nSOURCES: S1"
    response = client.post("/api/chat/stream", json={"question": "How long is the warranty?"})
    conversation_id = _events(response.text)[-1][1]["conversation_id"]

    response = client.post(
        "/api/chat/regenerate",
        json={"conversation_id": conversation_id, "document_ids": [first["id"]]},
    )

    done = _events(response.text)[-1][1]
    assert all(source["filename"] == "policy.pdf" for source in done["assistant_message"]["sources"])


# ---------------------------------------------------------------- conversation search

def _conversation(client, streamed, question, answer):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    streamed["text"] = f"{answer}\nSOURCES: S1"
    response = client.post("/api/chat/stream", json={"question": question})
    return _events(response.text)[-1][1]["conversation_id"]


def test_search_matches_conversation_titles(client, streamed):
    _conversation(client, streamed, "How long is the warranty?", "Two years.")
    _conversation(client, streamed, "How do I clean the jar?", "Use warm water.")

    body = client.get("/api/conversations", params={"q": "warranty"}).json()

    assert [item["title"] for item in body["conversations"]] == ["How long is the warranty?"]


def test_search_also_matches_the_text_of_messages(client, streamed):
    _conversation(client, streamed, "warranty length", "The warranty covers motor defects and a zeppelin part.")
    _conversation(client, streamed, "warranty cover", "Nothing special here.")

    body = client.get("/api/conversations", params={"q": "zeppelin"}).json()

    assert [item["title"] for item in body["conversations"]] == ["warranty length"]


def test_search_is_case_insensitive_and_treats_percent_as_text(client, streamed):
    _conversation(client, streamed, "Discount 50% off", "Answer text.")
    _conversation(client, streamed, "Other chat", "Answer text.")

    assert len(client.get("/api/conversations", params={"q": "DISCOUNT"}).json()["conversations"]) == 1
    assert len(client.get("/api/conversations", params={"q": "50%"}).json()["conversations"]) == 1
    assert client.get("/api/conversations", params={"q": "%"}).json()["total"] == 1


def test_empty_search_lists_everything(client, streamed):
    _conversation(client, streamed, "One", "A.")
    _conversation(client, streamed, "Two", "B.")
    assert client.get("/api/conversations", params={"q": "   "}).json()["total"] == 2
