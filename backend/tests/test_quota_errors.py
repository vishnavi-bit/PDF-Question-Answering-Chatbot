"""Gemini quota errors: clear messages, no repeated Gemini calls while the quota is used up, no 500 errors."""

from __future__ import annotations

import pytest

from app.services import llm_service
from app.services.llm_service import LLMError
from tests.helpers import upload_pdf

QUOTA_ERROR = "The Gemini free-tier rate limit or daily quota was reached. Wait a minute and try again."


def _message(role_text: str) -> list[dict]:
    return [{"role": "user", "content": role_text}]


def test_quota_error_stops_new_gemini_requests_for_a_while(monkeypatch):
    sent = []

    def fake_gemini(*args, **kwargs):
        sent.append(1)
        raise LLMError(429, "rate_limited", QUOTA_ERROR)

    monkeypatch.setattr(llm_service, "_complete_uncached", fake_gemini)
    with pytest.raises(LLMError) as first:
        llm_service.complete("system", _message("first question"))
    assert first.value.code == "rate_limited"

    with pytest.raises(LLMError) as second:
        llm_service.complete("system", _message("a different question"))
    assert second.value.status_code == 429
    assert second.value.code == "quota_exhausted"
    assert "no request was sent" in second.value.message
    assert len(sent) == 1  # the second request never reached Gemini


def test_gemini_is_tried_again_after_the_quota_cooldown(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(llm_service._breaker, "_clock", lambda: now[0])
    sent = []

    def fake_gemini(*args, **kwargs):
        sent.append(1)
        if len(sent) == 1:
            raise LLMError(429, "rate_limited", QUOTA_ERROR)
        return '{"answer": "ok"}'

    monkeypatch.setattr(llm_service, "_complete_uncached", fake_gemini)
    with pytest.raises(LLMError):
        llm_service.complete("system", _message("question one"))

    now[0] += get_cooldown() + 1
    assert llm_service.complete("system", _message("question two")) == '{"answer": "ok"}'
    assert len(sent) == 2


def get_cooldown() -> float:
    from app.core.config import get_settings
    return get_settings().gemini_quota_cooldown_seconds


def test_breaker_status_says_why_it_is_open(monkeypatch):
    monkeypatch.setattr(llm_service, "_complete_uncached", lambda *a, **k: (_ for _ in ()).throw(LLMError(429, "rate_limited", QUOTA_ERROR)))
    with pytest.raises(LLMError):
        llm_service.complete("system", _message("question"))
    status = llm_service.breaker_status()
    assert status["open"] is True and status["reason"] == "quota"


def test_mind_map_during_quota_exhaustion_returns_429_with_a_clear_message(client, llm):
    doc = upload_pdf(client, ["Motor power is 750 watts and the warranty is two years."], name="quota.pdf").json()["document"]
    llm.error = LLMError(429, "rate_limited", QUOTA_ERROR)
    response = client.post("/api/study/mind-maps", json={"document_ids": [doc["id"]]})
    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()
    assert response.json()["code"] == "rate_limited"


@pytest.mark.parametrize("path, body", [
    ("/api/study/notes/saved", {"mode": "overview", "length": "short", "document_ids": []}),
    ("/api/study/mock-exams", {"difficulty": "easy", "mcq_count": 3, "descriptive_count": 0, "duration_minutes": 10, "document_ids": []}),
])
def test_study_tools_never_show_internal_server_error_for_quota(client, llm, path, body):
    upload_pdf(client, ["Motor power is 750 watts and the warranty is two years."], name="quota2.pdf")
    llm.error = LLMError(429, "rate_limited", QUOTA_ERROR)
    response = client.post(path, json=body)
    assert response.status_code == 429, response.text
    assert "internal" not in response.text.lower()
    assert "quota" in response.json()["detail"].lower()
