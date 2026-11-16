"""
Retry and error-handling tests for the Gemini service.

A scripted fake client returns a list of results in order: an exception to raise,
or a successful reply. No network calls are made, and waits are skipped.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Message
from app.services import llm_service
from app.services.llm_service import LLMError
from tests.helpers import upload_pdf


class ScriptedModels:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.timeouts = []

    def generate_content(self, **kwargs):
        self.calls += 1
        self.timeouts.append(kwargs["config"].http_options.timeout)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item)


def _error(code: int, message: str = "provider said no", status: str = "UNAVAILABLE", headers=None):
    response = SimpleNamespace(headers=headers or {})
    return genai_errors.APIError(code, {"error": {"code": code, "message": message, "status": status}}, response)


def _client_error(code: int, message: str = "nope", status: str = "ERR", headers=None):
    response = SimpleNamespace(headers=headers or {})
    return genai_errors.ClientError(code, {"error": {"code": code, "message": message, "status": status}}, response)


def _server_error(code: int, message: str = "busy", status: str = "UNAVAILABLE"):
    return genai_errors.ServerError(code, {"error": {"code": code, "message": message, "status": status}}, None)


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key-not-real")
    monkeypatch.setattr(get_settings(), "gemini_model", "gemini-test-model")

    def install(script):
        models = ScriptedModels(script)
        monkeypatch.setattr(llm_service, "_client", SimpleNamespace(models=models))
        return models

    return install


def _ask():
    return llm_service.complete("Sys", [{"role": "user", "content": "Question?"}], json_output=True)


# ---------------------------------------------------------------- retries that should happen


def test_503_is_retried_and_the_second_attempt_succeeds(scripted):
    models = scripted([_server_error(503), '{"answer": "ok", "source_ids": []}'])
    assert _ask() == '{"answer": "ok", "source_ids": []}'
    assert models.calls == 2


def test_504_is_retried_and_the_third_attempt_succeeds(scripted):
    models = scripted([_server_error(504), _server_error(504), "final answer"])
    assert _ask() == "final answer"
    assert models.calls == 3


def test_retries_stop_after_three_attempts_for_503(scripted):
    models = scripted([_server_error(503), _server_error(503), _server_error(503), "never reached"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 3  # never a fourth attempt
    assert info.value.status_code == 503
    assert info.value.code == "gemini_unavailable"
    assert "3 times" in info.value.message


def test_504_after_all_attempts_becomes_a_504_not_a_502(scripted):
    models = scripted([_server_error(504), _server_error(504), _server_error(504)])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 3
    assert info.value.status_code == 504
    assert info.value.code == "gemini_timeout"


def test_429_with_short_retry_after_is_retried(scripted, monkeypatch):
    waits = []
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: waits.append(seconds))
    models = scripted([_client_error(429, status="RESOURCE_EXHAUSTED", headers={"retry-after": "2"}), "ok"])
    assert _ask() == "ok"
    assert models.calls == 2
    assert 2 <= waits[0] <= 2 + llm_service.MAX_JITTER_SECONDS


def test_429_without_retry_after_is_not_retried(scripted):
    models = scripted([_client_error(429, status="RESOURCE_EXHAUSTED"), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 429


def test_429_with_long_retry_after_is_not_retried(scripted):
    models = scripted([_client_error(429, status="RESOURCE_EXHAUSTED", headers={"retry-after": "3600"}), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 429


def test_daily_quota_429_is_never_retried_even_with_retry_after(scripted):
    models = scripted(
        [_client_error(429, message="Quota exceeded for metric: free tier requests per day", status="RESOURCE_EXHAUSTED", headers={"retry-after": "2"}), "never"]
    )
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 429


def test_backoff_grows_between_attempts(scripted, monkeypatch):
    waits = []
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: waits.append(seconds))
    scripted([_server_error(503), _server_error(503), "ok"])
    _ask()
    assert len(waits) == 2
    assert 1.0 <= waits[0] <= 1.0 + llm_service.MAX_JITTER_SECONDS
    assert 2.0 <= waits[1] <= 2.0 + llm_service.MAX_JITTER_SECONDS
    assert waits[1] > waits[0]


def test_total_time_budget_stops_retries_early(scripted, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(llm_service, "_monotonic", lambda: clock["now"])

    def fake_sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(llm_service, "_sleep", fake_sleep)
    monkeypatch.setattr(get_settings(), "gemini_total_time_budget_seconds", 20.0)

    class SlowModels(ScriptedModels):
        def generate_content(self, **kwargs):
            clock["now"] += 15.0  # each attempt takes 15 seconds
            return super().generate_content(**kwargs)

    models = SlowModels([_server_error(504), _server_error(504), _server_error(504)])
    monkeypatch.setattr(llm_service, "_client", SimpleNamespace(models=models))

    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls < 3  # the budget stopped it before the last attempt
    assert info.value.status_code == 504


def test_each_attempt_timeout_fits_inside_the_remaining_budget(scripted, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(llm_service, "_monotonic", lambda: clock["now"])
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setattr(get_settings(), "gemini_timeout_seconds", 90.0)
    monkeypatch.setattr(get_settings(), "gemini_total_time_budget_seconds", 150.0)

    models = scripted([_server_error(503), "ok"])
    _ask()
    assert models.timeouts[0] == 90_000  # first attempt uses the normal per-request timeout
    assert all(timeout <= 150_000 for timeout in models.timeouts)


# ---------------------------------------------------------------- errors that must NOT be retried


def test_invalid_api_key_is_not_retried(scripted):
    models = scripted([_client_error(401, status="UNAUTHENTICATED"), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 503
    assert info.value.code == "auth_failed"


def test_bad_request_is_not_retried(scripted):
    models = scripted([_client_error(400, status="INVALID_ARGUMENT"), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 502
    assert info.value.code == "bad_request"


def test_unknown_model_is_not_retried(scripted):
    models = scripted([_client_error(404, status="NOT_FOUND"), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.code == "model_not_found"


def test_client_side_timeout_is_not_retried(scripted):
    models = scripted([TimeoutError("slow"), "never"])
    with pytest.raises(LLMError) as info:
        _ask()
    assert models.calls == 1
    assert info.value.status_code == 504
    assert info.value.code == "timeout"


def test_provider_error_details_and_key_do_not_reach_the_user(scripted, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-secret-test-value")
    scripted([_server_error(503, message="internal stack trace detail")] * 3)
    with pytest.raises(LLMError) as info:
        _ask()
    assert "AIza-secret-test-value" not in info.value.message
    assert "internal stack trace" not in info.value.message


# ---------------------------------------------------------------- end-to-end through the API


def test_chat_retries_then_succeeds_and_saves_exactly_one_pair(client, scripted):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."])
    models = scripted([_server_error(503), '{"answer": "Two years.", "source_ids": ["S1"]}'])

    response = client.post("/api/chat", json={"question": "How long is the warranty?"})

    assert response.status_code == 200
    assert models.calls == 2
    body = response.json()
    assert body["assistant_message"]["content"] == "Two years."
    assert body["assistant_message"]["sources"][0]["page_number"] == 1
    session = SessionLocal()
    try:
        assert session.query(Message).count() == 2  # one question + one answer, no duplicates
    finally:
        session.close()


def test_chat_after_final_504_returns_504_and_saves_nothing(client, scripted):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."])
    scripted([_server_error(504), _server_error(504), _server_error(504)])

    response = client.post("/api/chat", json={"question": "How long is the warranty?"})

    assert response.status_code == 504
    assert "tried 3 times" in response.json()["detail"]
    assert "Traceback" not in response.text
    session = SessionLocal()
    try:
        assert session.query(Message).count() == 0  # the failed question is not saved
    finally:
        session.close()


def test_chat_with_missing_key_still_returns_clear_503(client, monkeypatch):
    upload_pdf(client, ["The warranty lasts two years from the date of purchase."])
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(llm_service, "_client", None)

    response = client.post("/api/chat", json={"question": "How long is the warranty?"})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
