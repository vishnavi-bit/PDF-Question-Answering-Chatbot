"""Answer cache, concurrent de-duplication, request guard, and duplicate-record protection. Mocks only."""

from __future__ import annotations

import threading
import time

import pytest

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import StudySet
from app.services import llm_service
from app.services.llm_service import LLMError
from app.services.request_guard import RequestGuard, RequestInProgress, chat_guard
from tests.gemini_fakes import FakeClock, api_error, install
from tests.helpers import upload_pdf

EXCERPTS_A = [{"role": "user", "content": "Document excerpts: warranty is two years. Question: how long?"}]
EXCERPTS_B = [{"role": "user", "content": "Document excerpts: cleaning uses warm water. Question: how long?"}]


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(llm_service, "_monotonic", fake)
    monkeypatch.setattr(llm_service, "_breaker", llm_service.CircuitBreaker(clock=fake))
    monkeypatch.setattr(llm_service, "_cache", llm_service._AnswerCache(clock=fake))
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 900.0)
    monkeypatch.setattr(get_settings(), "gemini_cache_max_entries", 200)
    return fake


# ---------------------------------------------------------------- the answer cache

def test_identical_prompt_is_answered_from_the_cache(monkeypatch, clock):
    client = install(monkeypatch, ["Two years."])
    first = llm_service.complete("System.", EXCERPTS_A, json_output=True)
    second = llm_service.complete("System.", EXCERPTS_A, json_output=True)
    assert first == second == "Two years."
    assert client.complete_calls == 1


def test_different_document_selection_never_reuses_an_answer(monkeypatch, clock):
    client = install(monkeypatch, ["Two years.", "Warm water."])
    llm_service.complete("System.", EXCERPTS_A)
    llm_service.complete("System.", EXCERPTS_B)  # other PDFs -> other excerpts -> new call
    assert client.complete_calls == 2


def test_different_generation_options_are_cached_separately(monkeypatch, clock):
    client = install(monkeypatch, ["text", '{"a": 1}', "short"])
    llm_service.complete("System.", EXCERPTS_A, json_output=False)
    llm_service.complete("System.", EXCERPTS_A, json_output=True)
    llm_service.complete("System.", EXCERPTS_A, max_tokens=50)
    assert client.complete_calls == 3


def test_a_different_model_is_a_different_cache_entry(monkeypatch, clock):
    client = install(monkeypatch, ["one", "two"])
    llm_service.complete("System.", EXCERPTS_A)
    monkeypatch.setattr(get_settings(), "gemini_model", "gemini-other-model")
    llm_service.complete("System.", EXCERPTS_A)
    assert client.complete_calls == 2


def test_cached_answers_expire(monkeypatch, clock):
    client = install(monkeypatch, ["first", "second"])
    llm_service.complete("System.", EXCERPTS_A)
    clock.advance(901)
    assert llm_service.complete("System.", EXCERPTS_A) == "second"
    assert client.complete_calls == 2


def test_cache_keeps_only_the_configured_number_of_answers(monkeypatch, clock):
    monkeypatch.setattr(get_settings(), "gemini_cache_max_entries", 2)
    client = install(monkeypatch, ["a", "b", "c", "a-again"])
    for text in ["A", "B", "C"]:
        llm_service.complete("System.", [{"role": "user", "content": text}])
    assert client.complete_calls == 3
    # "A" was the oldest and has been evicted, so it is asked again
    assert llm_service.complete("System.", [{"role": "user", "content": "A"}]) == "a-again"


def test_cache_can_be_turned_off(monkeypatch, clock):
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 0.0)
    client = install(monkeypatch, ["one", "two"])
    llm_service.complete("System.", EXCERPTS_A)
    llm_service.complete("System.", EXCERPTS_A)
    assert client.complete_calls == 2


def test_failed_answers_are_never_cached(monkeypatch, clock):
    client = install(monkeypatch, [api_error(401, status="UNAUTHENTICATED"), "fixed"])
    with pytest.raises(LLMError):
        llm_service.complete("System.", EXCERPTS_A)
    assert llm_service.complete("System.", EXCERPTS_A) == "fixed"
    assert client.complete_calls == 2


def test_cached_answers_still_work_during_a_cooldown(monkeypatch, clock):
    client = install(monkeypatch, ["good answer"] + [api_error(503)] * 9)
    assert llm_service.complete("System.", EXCERPTS_A) == "good answer"
    for index in range(3):
        with pytest.raises(LLMError):
            llm_service.complete("System.", [{"role": "user", "content": f"outage {index}"}])
    assert llm_service.breaker_status()["open"] is True

    assert llm_service.complete("System.", EXCERPTS_A) == "good answer"  # served from the cache
    assert client.complete_calls == 1 + 9


# ---------------------------------------------------------------- concurrent identical calls

def test_identical_concurrent_calls_share_one_gemini_request(monkeypatch, clock):
    release = threading.Event()
    started = threading.Event()

    class SlowClient:
        complete_calls = 0

        def __init__(self):
            self.models = self

        def generate_content(self, *, model, contents, config):
            SlowClient.complete_calls += 1
            started.set()
            release.wait(5)
            from types import SimpleNamespace
            return SimpleNamespace(text="Shared answer.", usage_metadata=None)

    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-test-key-not-real")
    monkeypatch.setattr(llm_service, "_client", SlowClient())
    results: list[str] = []
    errors_seen: list[BaseException] = []

    def ask():
        try:
            results.append(llm_service.complete("System.", EXCERPTS_A))
        except BaseException as exc:  # pragma: no cover - reported by the assertions below
            errors_seen.append(exc)

    first = threading.Thread(target=ask)
    first.start()
    started.wait(5)
    second = threading.Thread(target=ask)
    second.start()
    time.sleep(0.1)
    release.set()
    first.join(5)
    second.join(5)

    assert errors_seen == []
    assert results == ["Shared answer.", "Shared answer."]
    assert SlowClient.complete_calls == 1


def test_a_failure_is_shared_with_the_waiting_caller_and_not_remembered(monkeypatch, clock):
    release = threading.Event()
    started = threading.Event()
    calls = []

    class FailingClient:
        def __init__(self):
            self.models = self

        def generate_content(self, *, model, contents, config):
            calls.append(1)
            started.set()
            release.wait(5)
            raise api_error(400, status="INVALID_ARGUMENT")

    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-test-key-not-real")
    monkeypatch.setattr(llm_service, "_client", FailingClient())
    outcomes = []

    def ask():
        try:
            llm_service.complete("System.", EXCERPTS_A)
            outcomes.append("ok")
        except LLMError as exc:
            outcomes.append(exc.code)

    a = threading.Thread(target=ask)
    a.start()
    started.wait(5)
    b = threading.Thread(target=ask)
    b.start()
    time.sleep(0.1)
    release.set()
    a.join(5)
    b.join(5)

    assert outcomes == ["bad_request", "bad_request"]
    assert len(calls) == 1


# ---------------------------------------------------------------- request guard (chat and study)

def test_request_guard_returns_the_stored_result_for_repeats():
    guard = RequestGuard("test", clock=FakeClock())
    key = RequestGuard.make_key("quiz", 5, ["doc-a"])
    fresh, _ = guard.acquire(key)
    assert fresh is True
    guard.complete(key, {"quiz_id": 7})

    fresh_again, stored = guard.acquire(key)

    assert fresh_again is False
    assert stored == {"quiz_id": 7}


def test_request_guard_forgets_results_after_the_ttl(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(get_settings(), "request_dedupe_ttl_seconds", 120.0)
    guard = RequestGuard("test", clock=clock)
    key = RequestGuard.make_key("notes")
    guard.acquire(key)
    guard.complete(key, "first")
    clock.advance(121)

    fresh, _ = guard.acquire(key)

    assert fresh is True


def test_request_guard_does_not_remember_failures():
    guard = RequestGuard("test", clock=FakeClock())
    key = RequestGuard.make_key("exam", 3)
    guard.acquire(key)
    guard.abandon(key, RuntimeError("boom"))

    fresh, _ = guard.acquire(key)

    assert fresh is True  # a failed request may be retried


def test_request_guard_refuses_a_second_copy_while_the_first_is_running():
    guard = RequestGuard("test", clock=FakeClock())
    key = RequestGuard.make_key("chat", "same")
    guard.acquire(key)
    with pytest.raises(RequestInProgress):
        guard.acquire(key)


def test_keys_change_when_the_document_selection_or_options_change():
    base = RequestGuard.make_key("quiz", 5, ["doc-a"])
    assert base != RequestGuard.make_key("quiz", 10, ["doc-a"])
    assert base != RequestGuard.make_key("quiz", 5, ["doc-a", "doc-b"])
    assert base == RequestGuard.make_key("quiz", 5, ["doc-a"])


# ---------------------------------------------------------------- duplicate records

def test_repeated_chat_request_with_the_same_id_saves_one_exchange(client, llm):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."], name="p.pdf")
    body = {"question": "How long is the warranty?", "client_request_id": "req-123"}

    first = client.post("/api/chat", json=body).json()
    second = client.post("/api/chat", json=body).json()

    assert second["assistant_message"]["id"] == first["assistant_message"]["id"]
    assert len(llm.calls) == 1
    detail = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assert len(detail["messages"]) == 2


def test_different_request_ids_are_separate_questions(client, llm):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."], name="p.pdf")
    client.post("/api/chat", json={"question": "How long is the warranty?", "client_request_id": "a"})
    client.post("/api/chat", json={"question": "How long is the warranty?", "client_request_id": "b"})
    assert len(llm.calls) == 2


def test_failed_chat_request_can_be_retried_with_the_same_id(client, llm):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."], name="p.pdf")
    body = {"question": "How long is the warranty?", "client_request_id": "retry-me"}
    from app.services.llm_service import LLMError as Err

    llm.error = Err(504, "gemini_timeout", "Gemini did not finish the answer in time.")
    assert client.post("/api/chat", json=body).status_code == 504

    llm.error = None
    response = client.post("/api/chat", json=body)

    assert response.status_code == 200
    session = SessionLocal()
    try:
        from app.database.models import Message

        assert session.query(Message).count() == 2  # only the successful exchange was saved
    finally:
        session.close()


def test_identical_study_requests_return_the_same_record(client, llm):
    document = upload_pdf(client, ["The warranty covers motor defects for two years."], name="s.pdf").json()["document"]
    import json as _json

    llm.reply = _json.dumps({"questions": [{
        "question": "How long is the warranty?", "options": ["1", "2", "3", "4"], "correct_index": 1,
        "explanation": "Two years.", "topic": "Warranty", "source_ids": ["S1"],
    }]})
    body = {"count": 5, "document_ids": [document["id"]]}

    first = client.post("/api/study/quizzes", json=body).json()
    second = client.post("/api/study/quizzes", json=body).json()

    assert first["id"] == second["id"]
    session = SessionLocal()
    try:
        assert session.query(StudySet).filter_by(kind="quiz").count() == 1
    finally:
        session.close()


def test_study_requests_for_different_pdfs_are_not_shared(client, llm):
    first_doc = upload_pdf(client, ["The warranty covers motor defects for two years."], name="a.pdf").json()["document"]
    second_doc = upload_pdf(client, ["Clean the jar with warm water after each use."], name="b.pdf").json()["document"]
    import json as _json

    llm.reply = _json.dumps({"questions": [{
        "question": "What is covered?", "options": ["1", "2", "3", "4"], "correct_index": 0,
        "explanation": "Motor.", "topic": "T", "source_ids": ["S1"],
    }]})

    one = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [first_doc["id"]]}).json()
    two = client.post("/api/study/quizzes", json={"count": 5, "document_ids": [second_doc["id"]]}).json()

    assert one["id"] != two["id"]


def test_chat_guard_is_cleared_between_tests_by_the_fixture():
    assert chat_guard.acquire(RequestGuard.make_key("probe"))[0] is True
