"""
Gemini streaming with mocks: text as it arrives, errors before and during the answer,
client disconnects, and the /api/chat/stream endpoint (SSE events, nothing saved on failure).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Message
from app.services import llm_service
from app.services.llm_service import LLMError
from tests.gemini_fakes import FakeClock, api_error, install
from tests.helpers import upload_pdf

WARRANTY = "The warranty covers motor defects for two years from the date of purchase."
MSG = [{"role": "user", "content": "How long is the warranty?"}]


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(llm_service, "_monotonic", fake)
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: fake.advance(seconds))
    monkeypatch.setattr(llm_service, "_breaker", llm_service.CircuitBreaker(clock=fake))
    monkeypatch.setattr(llm_service, "_cache", llm_service._AnswerCache(clock=fake))
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 0.0)
    return fake


def _read_events(response_text: str) -> list[tuple[str, dict]]:
    events = []
    for block in response_text.strip().split("\n\n"):
        name = ""
        data = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name:
            events.append((name, data))
    return events


# ---------------------------------------------------------------- the streaming client

def test_stream_yields_pieces_in_order_and_remembers_the_full_answer(monkeypatch, clock):
    install(monkeypatch, [["The warranty ", "lasts ", "two years."]])
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 900.0)

    pieces = list(llm_service.stream_text("System.", MSG))

    assert pieces == ["The warranty ", "lasts ", "two years."]
    # the same question is now answered from the cache without a Gemini call
    cached = list(llm_service.stream_text("System.", MSG))
    assert cached == ["The warranty lasts two years."]


def test_error_before_any_text_is_retried(monkeypatch, clock):
    client = install(monkeypatch, [api_error(503), ["Recovered ", "answer."]])
    assert "".join(llm_service.stream_text("System.", MSG)) == "Recovered answer."
    assert client.stream_calls == 2


def test_error_before_any_text_after_three_attempts_raises_before_yielding(monkeypatch, clock):
    client = install(monkeypatch, [api_error(504), api_error(504), api_error(504)])
    stream = llm_service.stream_text("System.", MSG)
    with pytest.raises(LLMError) as info:
        next(stream)
    assert client.stream_calls == 3
    assert info.value.status_code == 504


def test_error_after_some_text_is_not_retried_and_is_reported(monkeypatch, clock):
    client = install(monkeypatch, [["The warranty "] + [api_error(503)]])
    stream = llm_service.stream_text("System.", MSG)
    assert next(stream) == "The warranty "
    with pytest.raises(LLMError) as info:
        next(stream)
    assert client.stream_calls == 1  # never restarted halfway through an answer
    assert info.value.code == "stream_interrupted"


def test_interrupted_answer_is_not_cached(monkeypatch, clock):
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 900.0)
    install(monkeypatch, [["Partial "] + [httpx.ReadError("connection dropped")]])
    stream = llm_service.stream_text("System.", MSG)
    next(stream)
    with pytest.raises(LLMError):
        next(stream)
    assert llm_service._cache.get(llm_service._cache_key(
        get_settings().gemini_model, "System.", MSG, None, False, "")) is None


def test_connection_drop_mid_stream_is_reported_as_interrupted(monkeypatch, clock):
    install(monkeypatch, [["Half "] + [httpx.RemoteProtocolError("server closed")]])
    stream = llm_service.stream_text("System.", MSG)
    assert next(stream) == "Half "
    with pytest.raises(LLMError) as info:
        next(stream)
    assert info.value.code == "stream_interrupted"


def test_client_disconnect_is_not_counted_as_a_failure(monkeypatch, clock):
    install(monkeypatch, [["First ", "second ", "third"]])
    stream = llm_service.stream_text("System.", MSG)
    assert next(stream) == "First "
    stream.close()  # the browser went away
    assert llm_service.breaker_status()["consecutive_failures"] == 0


def test_stream_stops_when_the_total_time_budget_is_used_up(monkeypatch, clock):
    monkeypatch.setattr(get_settings(), "gemini_total_time_budget_seconds", 10.0)

    class SlowStream:
        def __init__(self):
            self.count = 0

        def __iter__(self):
            return self

        def __next__(self):
            self.count += 1
            clock.advance(6)  # each piece takes 6 seconds
            if self.count > 10:
                raise StopIteration
            from types import SimpleNamespace
            return SimpleNamespace(text="x")

    from types import SimpleNamespace

    class Models:
        def generate_content_stream(self, **kwargs):
            return SlowStream()

    monkeypatch.setattr(llm_service, "_client", SimpleNamespace(models=Models()))
    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-test-key-not-real")
    stream = llm_service.stream_text("System.", MSG)
    with pytest.raises(LLMError) as info:
        list(stream)
    assert info.value.status_code == 504


def test_stream_without_a_key_fails_before_any_request(monkeypatch, clock):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(llm_service, "_client", None)
    stream = llm_service.stream_text("System.", MSG)
    with pytest.raises(LLMError) as info:
        next(stream)
    assert info.value.code == "not_configured"


def test_cooldown_blocks_streams_too(monkeypatch, clock):
    client = install(monkeypatch, [api_error(503)] * 9)
    for index in range(3):
        with pytest.raises(LLMError):
            list(llm_service.stream_text("System.", [{"role": "user", "content": f"s{index}"}]))
    with pytest.raises(LLMError) as info:
        next(llm_service.stream_text("System.", [{"role": "user", "content": "blocked"}]))
    assert info.value.code == "cooldown"


# ---------------------------------------------------------------- the chat streaming endpoint

def _stream_chat(client, body):
    return client.post("/api/chat/stream", json=body)


def test_chat_stream_sends_text_then_saves_one_answer_with_its_source(client, llm, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")

    def fake_stream(system, messages, max_tokens=None, json_output=False):
        assert json_output is False
        yield "The warranty lasts two years "
        yield "from the date of purchase.\n"
        yield "SOURCES: S1"

    monkeypatch.setattr(llm_service, "stream_text", fake_stream)

    response = _stream_chat(client, {"question": "How long is the warranty?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _read_events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-1] == "done"
    streamed = "".join(data["text"] for name, data in events if name == "delta")
    assert "SOURCES" not in streamed  # the citation line is never shown as text
    assert streamed.strip().startswith("The warranty lasts two years")
    done = events[-1][1]
    assert done["assistant_message"]["content"].startswith("The warranty lasts two years")
    source = done["assistant_message"]["sources"][0]
    assert source["filename"] == "policy.pdf"
    assert source["page_number"] == 1
    session = SessionLocal()
    try:
        assert session.query(Message).count() == 2
    finally:
        session.close()


def test_chat_stream_without_a_sources_line_claims_no_sources(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    monkeypatch.setattr(llm_service, "stream_text", lambda *a, **k: iter(["Two years, I think."]))

    events = _read_events(_stream_chat(client, {"question": "How long is the warranty?"}).text)

    done = events[-1][1]
    assert done["assistant_message"]["sources"] == []
    assert done["answered_from_documents"] is False


def test_chat_stream_says_none_when_the_excerpts_do_not_answer(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    monkeypatch.setattr(llm_service, "stream_text", lambda *a, **k: iter(["Not in the documents.\nSOURCES: none"]))

    events = _read_events(_stream_chat(client, {"question": "How long is the warranty?"}).text)

    assert events[-1][1]["assistant_message"]["sources"] == []


def test_chat_stream_unknown_source_ids_are_not_cited(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    monkeypatch.setattr(llm_service, "stream_text", lambda *a, **k: iter(["Two years.\nSOURCES: S9"]))

    events = _read_events(_stream_chat(client, {"question": "How long is the warranty?"}).text)

    assert events[-1][1]["assistant_message"]["sources"] == []


def test_chat_stream_failure_before_text_is_an_http_error_and_saves_nothing(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    install(monkeypatch, [api_error(504), api_error(504), api_error(504)])

    response = _stream_chat(client, {"question": "How long is the warranty?"})

    assert response.status_code == 504
    assert response.headers["content-type"].startswith("application/json")
    assert "tried 3 times" in response.json()["detail"]
    assert client.get("/api/conversations").json()["total"] == 0


def test_chat_stream_failure_mid_answer_sends_an_error_event_and_saves_nothing(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")

    def broken(*args, **kwargs):
        yield "The warranty lasts "
        raise LLMError(502, "stream_interrupted", "The answer was interrupted while Gemini was writing it.")

    monkeypatch.setattr(llm_service, "stream_text", broken)

    response = _stream_chat(client, {"question": "How long is the warranty?"})

    events = _read_events(response.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["status"] == 502
    assert "interrupted" in events[-1][1]["detail"]
    assert client.get("/api/conversations").json()["total"] == 0


def test_chat_stream_during_cooldown_is_refused_with_503(client, monkeypatch, clock):
    upload_pdf(client, [WARRANTY], name="policy.pdf")
    install(monkeypatch, [api_error(503)] * 9)
    for index in range(3):
        with pytest.raises(LLMError):
            llm_service.complete("System.", [{"role": "user", "content": f"x{index}"}])

    response = _stream_chat(client, {"question": "How long is the warranty?"})

    assert response.status_code == 503
    assert "try again in about" in response.json()["detail"]


def test_chat_stream_question_without_documents_skips_gemini(client, monkeypatch, clock):
    called = []
    monkeypatch.setattr(llm_service, "stream_text", lambda *a, **k: called.append(1) or iter(["x"]))

    events = _read_events(_stream_chat(client, {"question": "zebra giraffe lions"}).text)

    assert called == []
    assert events[-1][0] == "done"
    assert events[-1][1]["answered_from_documents"] is False
