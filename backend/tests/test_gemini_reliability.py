"""
Gemini reliability with mocks: timeouts, 503, 504, rate limits, connection failures,
cooldown (circuit breaker), recovery, and what reaches the logs. No real API calls.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.core.config import get_settings
from app.services import llm_service
from app.services.llm_service import LLMError
from tests.gemini_fakes import FakeClock, api_error, install

MSG = [{"role": "user", "content": "Question about the warranty?"}]


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(llm_service, "_monotonic", fake)
    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: fake.advance(seconds))
    # the breaker and cache read the clock through their own closures, so rebuild them with the fake clock
    monkeypatch.setattr(llm_service, "_breaker", llm_service.CircuitBreaker(clock=fake))
    monkeypatch.setattr(llm_service, "_cache", llm_service._AnswerCache(clock=fake))
    monkeypatch.setattr(get_settings(), "gemini_cache_ttl_seconds", 0.0)  # no caching unless a test asks for it
    monkeypatch.setattr(get_settings(), "gemini_failure_threshold", 3)
    monkeypatch.setattr(get_settings(), "gemini_cooldown_seconds", 60.0)
    return fake


def _complete(text: str = "Question about the warranty?") -> str:
    return llm_service.complete("System rules.", [{"role": "user", "content": text}])


# ---------------------------------------------------------------- timeouts, 503, 504

def test_503_then_success_is_recovered_by_retry(monkeypatch, clock):
    client = install(monkeypatch, [api_error(503), "The warranty lasts two years."])
    assert _complete() == "The warranty lasts two years."
    assert client.complete_calls == 2
    assert llm_service.breaker_status()["consecutive_failures"] == 0


def test_504_then_success_is_recovered_by_retry(monkeypatch, clock):
    client = install(monkeypatch, [api_error(504), api_error(504), "Recovered answer."])
    assert _complete() == "Recovered answer."
    assert client.complete_calls == 3


def test_persistent_504_is_a_504_after_exactly_three_attempts(monkeypatch, clock):
    client = install(monkeypatch, [api_error(504)] * 3)
    with pytest.raises(LLMError) as info:
        _complete()
    assert client.complete_calls == 3
    assert info.value.status_code == 504
    assert info.value.code == "gemini_timeout"


def test_client_side_timeout_is_not_retried_and_is_a_504(monkeypatch, clock):
    client = install(monkeypatch, [TimeoutError("slow"), "never"])
    with pytest.raises(LLMError) as info:
        _complete()
    assert client.complete_calls == 1
    assert info.value.code == "timeout"


def test_each_attempt_timeout_is_passed_to_the_sdk(monkeypatch, clock):
    client = install(monkeypatch, [api_error(503), "ok"])
    _complete()
    assert all(timeout is not None and timeout <= 150_000 for timeout in client.timeouts)


# ---------------------------------------------------------------- rate limits

def test_rate_limit_without_retry_after_is_not_retried(monkeypatch, clock):
    client = install(monkeypatch, [api_error(429, status="RESOURCE_EXHAUSTED"), "never"])
    with pytest.raises(LLMError) as info:
        _complete()
    assert client.complete_calls == 1
    assert info.value.status_code == 429


def test_rate_limit_with_short_retry_after_recovers(monkeypatch, clock):
    client = install(monkeypatch, [api_error(429, status="RESOURCE_EXHAUSTED", headers={"retry-after": "2"}), "ok"])
    assert _complete() == "ok"
    assert client.complete_calls == 2


def test_quota_error_pauses_gemini_calls_instead_of_retrying_each_request(monkeypatch, clock):
    """A used-up quota does not recover in seconds: after the first quota error, no new Gemini requests are sent for a while."""
    script = [api_error(429, status="RESOURCE_EXHAUSTED"), "fine again"]
    client = install(monkeypatch, script)
    with pytest.raises(LLMError):
        _complete("question 0")
    for index in range(1, 6):
        with pytest.raises(LLMError) as blocked:
            _complete(f"question {index}")
        assert blocked.value.code == "quota_exhausted"
    assert client.complete_calls == 1  # only the first request reached Gemini
    assert llm_service.breaker_status()["reason"] == "quota"

    clock.advance(301)
    assert _complete("question later") == "fine again"
    assert client.complete_calls == 2


def test_daily_quota_is_never_retried_even_with_retry_after(monkeypatch, clock):
    client = install(monkeypatch, [api_error(429, status="RESOURCE_EXHAUSTED",
                                             message="Quota exceeded: free tier requests per day", headers={"retry-after": "2"}), "never"])
    with pytest.raises(LLMError):
        _complete()
    assert client.complete_calls == 1


# ---------------------------------------------------------------- connection failures

def test_connection_failure_is_retried_then_reported_without_internals(monkeypatch, clock):
    client = install(monkeypatch, [httpx.ConnectError("name resolution failed for generativelanguage.googleapis.com")] * 3)
    with pytest.raises(LLMError) as info:
        _complete()
    assert client.complete_calls == 3
    assert info.value.status_code == 503
    assert info.value.code == "gemini_unreachable"
    assert "internet connection" in info.value.message
    assert "googleapis" not in info.value.message


def test_connection_failure_then_recovery(monkeypatch, clock):
    install(monkeypatch, [httpx.ConnectError("boom"), "back online"])
    assert _complete() == "back online"


# ---------------------------------------------------------------- cooldown (circuit breaker)

def test_cooldown_opens_after_three_failed_calls_and_fails_fast(monkeypatch, clock):
    # 3 calls, each failing on every attempt with 503 -> breaker opens
    script = [api_error(503)] * (3 * 3)
    client = install(monkeypatch, script)
    for index in range(3):
        with pytest.raises(LLMError):
            _complete(f"q{index}")
    calls_before = client.complete_calls

    with pytest.raises(LLMError) as info:
        _complete("q-blocked")

    assert info.value.code == "cooldown"
    assert info.value.status_code == 503
    assert "try again in about" in info.value.message
    assert client.complete_calls == calls_before  # Gemini was not called at all
    assert llm_service.breaker_status()["open"] is True


def test_cooldown_ends_after_the_configured_time(monkeypatch, clock):
    script = [api_error(503)] * 9 + ["back"]
    client = install(monkeypatch, script)
    for index in range(3):
        with pytest.raises(LLMError):
            _complete(f"q{index}")
    with pytest.raises(LLMError):
        _complete("blocked")

    clock.advance(61)

    assert _complete("after the cooldown") == "back"
    assert llm_service.breaker_status() == {"open": False, "reason": None, "seconds_left": 0.0, "consecutive_failures": 0}


def test_a_failure_right_after_cooldown_reopens_it_immediately(monkeypatch, clock):
    script = [api_error(503)] * 9 + [api_error(503)] * 3
    client = install(monkeypatch, script)
    for index in range(3):
        with pytest.raises(LLMError):
            _complete(f"q{index}")
    clock.advance(61)
    calls_before = client.complete_calls

    with pytest.raises(LLMError) as info:
        _complete("probe after cooldown")

    assert client.complete_calls == calls_before + 3  # the probe really ran (3 attempts)
    assert llm_service.breaker_status()["open"] is True
    with pytest.raises(LLMError) as blocked:
        _complete("next request")
    assert blocked.value.code == "cooldown"


def test_a_success_clears_the_failure_count(monkeypatch, clock):
    install(monkeypatch, [api_error(503), "fine"])
    assert _complete("one") == "fine"
    assert llm_service.breaker_status()["consecutive_failures"] == 0


def test_timeouts_count_towards_the_cooldown(monkeypatch, clock):
    install(monkeypatch, [TimeoutError("slow")] * 3)
    for index in range(3):
        with pytest.raises(LLMError):
            _complete(f"slow{index}")
    with pytest.raises(LLMError) as info:
        _complete("blocked")
    assert info.value.code == "cooldown"


def test_bad_api_key_does_not_open_the_cooldown(monkeypatch, clock):
    client = install(monkeypatch, [api_error(401, status="UNAUTHENTICATED")] * 4)
    for index in range(4):
        with pytest.raises(LLMError) as info:
            _complete(f"k{index}")
        assert info.value.code == "auth_failed"
    assert llm_service.breaker_status()["open"] is False
    assert client.complete_calls == 4


def test_invalid_request_does_not_open_the_cooldown(monkeypatch, clock):
    install(monkeypatch, [api_error(400, status="INVALID_ARGUMENT")] * 4)
    for index in range(4):
        with pytest.raises(LLMError) as info:
            _complete(f"bad{index}")
        assert info.value.code == "bad_request"
    assert llm_service.breaker_status()["open"] is False


def test_missing_key_fails_before_any_request(monkeypatch, clock):
    client = install(monkeypatch, ["never"])
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    monkeypatch.setattr(llm_service, "_client", None)
    with pytest.raises(LLMError) as info:
        _complete()
    assert info.value.code == "not_configured"
    assert client.complete_calls == 0


# ---------------------------------------------------------------- logs never contain secrets or content

def test_logs_do_not_contain_the_api_key_or_the_pdf_text(monkeypatch, clock, caplog):
    secret_excerpt = "CONFIDENTIAL-PDF-SENTENCE-XYZ"
    install(monkeypatch, [api_error(503, message="Service overloaded for AIza-test-key-not-real?"), "ok"])
    caplog.set_level(logging.DEBUG)

    llm_service.complete("System rules.", [{"role": "user", "content": f"Excerpt: {secret_excerpt}"}])

    text = caplog.text
    assert "AIza-test-key-not-real" not in text
    assert secret_excerpt not in text
    assert "Excerpt:" not in text  # the prompt itself is never logged


# ---------------------------------------------------------------- recovery is visible in health

def test_health_reports_the_cooldown_without_secrets(client, monkeypatch, clock):
    install(monkeypatch, [api_error(503)] * 9)
    for index in range(3):
        with pytest.raises(LLMError):
            _complete(f"h{index}")

    body = client.get("/api/health").json()

    assert body["gemini_status"]["open"] is True
    assert "AIza" not in str(body)
