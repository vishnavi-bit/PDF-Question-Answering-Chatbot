"""
Gemini API wrapper (official Google Gen AI SDK: `google-genai`).

Reliability features:
- Retries (max 3 attempts) for temporary errors (503, 504, short 429, connection errors).
  Never retried: bad key, bad request, unknown model, daily quota, client timeouts.
- Total time budget per call, and a per-attempt timeout that fits inside it.
- Cooldown (circuit breaker): after repeated outage-type failures, calls fail fast for a
  short time instead of making every student wait. Cached answers still work.
- Request de-duplication: identical concurrent calls share one Gemini request.
- Answer cache: identical prompts (same excerpts, options, model) reuse the answer for a while.
- Streaming: text arrives as it is generated. Errors before the first text are retried and
  reported as HTTP errors; errors after it are raised to the caller as LLMError.

Security: the API key is read from backend settings only. It is never logged or returned.
Prompts and answers are never logged; only lengths, durations, status codes and key hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3              # total tries per call (1 first try + 2 retries)
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 8.0
MAX_JITTER_SECONDS = 0.5
MAX_RETRY_AFTER_SECONDS = 15.0
MIN_USEFUL_ATTEMPT_SECONDS = 10.0
CACHE_VERSION = "v1"          # bump when prompt formats change, so old cached answers are not reused

# Error codes that mean "Gemini is having trouble". They count towards the cooldown.
TRANSIENT_CODES = frozenset({"gemini_unavailable", "gemini_timeout", "timeout", "gemini_unreachable", "api_error", "stream_interrupted"})

# Test hooks: tests replace these to avoid real waiting or to control time.
_sleep: Callable[[float], None] = time.sleep
_monotonic: Callable[[], float] = time.monotonic

T = TypeVar("T")


class LLMError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


_client: genai.Client | None = None
_lock = threading.Lock()


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key.strip())


def _get_client() -> genai.Client:
    global _client
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        raise LLMError(
            503,
            "not_configured",
            "The Gemini API key is not configured. Add GEMINI_API_KEY to backend/.env and restart the server.",
        )
    with _lock:
        if _client is None:
            # The SDK's own retry stays off (default). Timeouts are set per request.
            _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# ---------------------------------------------------------------- cooldown (circuit breaker)

class CircuitBreaker:
    """Opens after `threshold` outage-type failures in a row. Half-open after the cooldown."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self.consecutive_failures = 0
        self.open_until = 0.0
        self.open_reason: str | None = None  # "outage" or "quota"

    def before_call(self) -> None:
        settings = get_settings()
        now = self._clock()
        with self._lock:
            if self.open_until and now < self.open_until:
                wait = math.ceil(self.open_until - now)
                if self.open_reason == "quota":
                    minutes = max(1, math.ceil(wait / 60))
                    raise LLMError(
                        429,
                        "quota_exhausted",
                        "The Gemini free-tier quota is used up for now, so no request was sent to Gemini. "
                        f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}, "
                        "or check your quota in Google AI Studio.",
                    )
                raise LLMError(
                    503,
                    "cooldown",
                    f"Gemini is temporarily unavailable after repeated errors. Please try again in about {wait} seconds.",
                )
            if self.open_until and now >= self.open_until:
                # Half-open: one more failure re-opens the circuit straight away.
                self.open_until = 0.0
                self.open_reason = None
                self.consecutive_failures = max(settings.gemini_failure_threshold - 1, 0)

    def on_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.open_until = 0.0
            self.open_reason = None

    def on_transient_failure(self) -> None:
        settings = get_settings()
        now = self._clock()
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= settings.gemini_failure_threshold:
                self.open_until = now + settings.gemini_cooldown_seconds
                self.open_reason = "outage"
                logger.warning(
                    "Gemini cooldown started for %.0f s after %d failures in a row",
                    settings.gemini_cooldown_seconds, self.consecutive_failures,
                )

    def on_quota_exhausted(self) -> None:
        """The free-tier quota is used up: stop sending Gemini requests for a while (no retry storm)."""
        settings = get_settings()
        now = self._clock()
        with self._lock:
            self.open_until = now + settings.gemini_quota_cooldown_seconds
            self.open_reason = "quota"
        logger.warning("Gemini quota reached: no new Gemini requests for %.0f s", settings.gemini_quota_cooldown_seconds)

    def status(self) -> dict[str, Any]:
        now = self._clock()
        with self._lock:
            remaining = max(0.0, self.open_until - now) if self.open_until else 0.0
            return {
                "open": remaining > 0,
                "reason": self.open_reason if remaining > 0 else None,
                "seconds_left": round(remaining, 1),
                "consecutive_failures": self.consecutive_failures,
            }

    def reset(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.open_until = 0.0
            self.open_reason = None


_breaker = CircuitBreaker(clock=lambda: _monotonic())


def breaker_status() -> dict[str, Any]:
    """Cooldown state for the health endpoint. Contains no secrets."""
    return _breaker.status()


# ---------------------------------------------------------------- answer cache and de-duplication

class _AnswerCache:
    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, key: str) -> str | None:
        now = self._clock()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires, text = item
            if expires <= now:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return text

    def put(self, key: str, text: str, ttl: float, max_entries: int) -> None:
        if ttl <= 0 or max_entries <= 0:
            return
        with self._lock:
            self._items[key] = (self._clock() + ttl, text)
            self._items.move_to_end(key)
            while len(self._items) > max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class _Call:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: str | None = None
        self.error: BaseException | None = None


_cache = _AnswerCache(clock=lambda: _monotonic())
_inflight: dict[str, _Call] = {}
_inflight_lock = threading.Lock()


def clear_cache() -> None:
    """Forget cached answers, breaker state and in-flight markers (used by tests)."""
    _cache.clear()
    _breaker.reset()
    with _inflight_lock:
        _inflight.clear()


def _cache_key(model: str, system: str, messages: list[dict[str, Any]], max_tokens: int | None,
               json_output: bool, thinking: str) -> str:
    """Everything that changes the answer. The messages hold the excerpts, so the PDF selection is included."""
    payload = json.dumps(
        {"v": CACHE_VERSION, "model": model, "system": system, "messages": messages,
         "max_tokens": max_tokens, "json": json_output, "thinking": thinking},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _singleflight_enter(key: str) -> tuple[bool, _Call]:
    with _inflight_lock:
        existing = _inflight.get(key)
        if existing is not None:
            return False, existing
        call = _Call()
        _inflight[key] = call
        return True, call


def _singleflight_leave(key: str, call: _Call, value: str | None = None, error: BaseException | None = None) -> None:
    with _inflight_lock:
        _inflight.pop(key, None)
    call.value = value
    call.error = error
    call.done.set()


# ---------------------------------------------------------------- request building and retries

def _to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    """Convert {role: user|assistant, content} into Gemini's format (assistant -> model)."""
    contents: list[types.Content] = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=message["content"])]))
    return contents


def _thinking_config() -> types.ThinkingConfig | None:
    """Optional thinking level from GEMINI_THINKING_LEVEL (minimal, low, medium or high). Empty = model default."""
    level = get_settings().gemini_thinking_level.strip()
    return types.ThinkingConfig(thinking_level=level.upper()) if level else None


def _retry_after_seconds(exc: errors.APIError) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _is_daily_quota(exc: errors.APIError) -> bool:
    """A used-up daily quota will not recover in seconds, so it is never retried."""
    text = f"{exc.status or ''} {exc.message or ''}".lower()
    return "per day" in text or "perday" in text or "daily" in text or "free_tier_requests" in text


def _backoff_seconds(attempt: int) -> float:
    base = min(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
    return base + random.uniform(0, MAX_JITTER_SECONDS)


def _log_success(response: Any, model: str, attempt: int, attempt_seconds: float, total_seconds: float) -> None:
    usage = getattr(response, "usage_metadata", None)
    logger.info(
        "Gemini OK: model=%s attempt=%d request_seconds=%.1f total_seconds=%.1f "
        "prompt_tokens=%s output_tokens=%s thought_tokens=%s",
        model, attempt, attempt_seconds, total_seconds,
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "thoughts_token_count", None),
    )


def _redact(text: str) -> str:
    """Remove the API key from any text before it is logged (defence in depth)."""
    key = get_settings().gemini_api_key.strip()
    if key and key in text:
        text = text.replace(key, "[redacted]")
    return text


def _log_provider_error(exc: errors.APIError, attempt: int, attempt_seconds: float) -> None:
    # Log what Google said (status and short message), never the key or the prompt.
    detail = _redact((exc.message or "").replace("\n", " "))[:200]
    logger.warning(
        "Gemini attempt %s failed after %.1f s: HTTP %s %s - %s",
        attempt, attempt_seconds, exc.code, exc.status, detail,
    )


def _retry_wait(exc: errors.APIError, attempt: int, limit: int = MAX_ATTEMPTS) -> float | None:
    """Seconds to wait before the next attempt, or None when the error must not be retried."""
    if attempt >= limit:
        return None
    if exc.code in (503, 504):
        return _backoff_seconds(attempt)
    if exc.code == 429 and not _is_daily_quota(exc):
        retry_after = _retry_after_seconds(exc)
        if retry_after is not None and retry_after <= MAX_RETRY_AFTER_SECONDS:
            return retry_after + random.uniform(0, MAX_JITTER_SECONDS)
    return None


def _map_api_error(exc: errors.APIError, model: str, attempts: int) -> LLMError:
    code = exc.code
    if code in (401, 403):
        return LLMError(503, "auth_failed", "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env.")
    if code == 404:
        return LLMError(502, "model_not_found", f"The Gemini model '{model}' was not found. Check GEMINI_MODEL in backend/.env.")
    if code == 429:
        return LLMError(
            429,
            "rate_limited",
            "The Gemini free-tier rate limit or daily quota was reached. Wait a minute and try again, "
            "or check your quota in Google AI Studio.",
        )
    if code == 503:
        return LLMError(503, "gemini_unavailable",
                        f"Gemini is temporarily unavailable (tried {attempts} times). Please try again in a minute.")
    if code == 504:
        return LLMError(504, "gemini_timeout",
                        f"Gemini did not finish the answer in time (tried {attempts} times). "
                        "Please try again, or ask a shorter or more specific question.")
    if code is not None and code >= 500:
        return LLMError(502, "api_error", "The Gemini API had a temporary problem. Please try again in a moment.")
    return LLMError(502, "bad_request", "Gemini could not process this request. Try a shorter question.")


def _with_retries(attempt_fn: Callable[[float], T], model: str, started: float,
                  max_attempts: int = MAX_ATTEMPTS, budget: float | None = None) -> tuple[T, int, float]:
    """
    Run attempt_fn(timeout_seconds) with retries. Returns (value, attempts, attempt_started).
    attempt_fn raises SDK errors (APIError), httpx errors or TimeoutError when it fails.
    """
    settings = get_settings()
    total_budget = budget if budget is not None else settings.gemini_total_time_budget_seconds
    attempt = 0
    while True:
        attempt += 1
        remaining = total_budget - (_monotonic() - started)
        timeout_seconds = min(settings.gemini_timeout_seconds, max(remaining, MIN_USEFUL_ATTEMPT_SECONDS))
        attempt_started = _monotonic()
        try:
            return attempt_fn(timeout_seconds), attempt, attempt_started
        except errors.APIError as exc:
            _log_provider_error(exc, attempt, _monotonic() - attempt_started)
            wait = _retry_wait(exc, attempt, max_attempts)
            elapsed = _monotonic() - started
            out_of_time = elapsed + (wait or 0) > total_budget
            if wait is not None and not out_of_time:
                _sleep(wait)
                continue
            raise _map_api_error(exc, model, attempt) from exc
        except (httpx.TimeoutException, TimeoutError) as exc:
            # A client-side timeout is not retried: the same long request would likely time out again.
            logger.warning("Gemini request timed out on attempt %s", attempt)
            raise LLMError(504, "timeout",
                           "Gemini took too long to answer. Please try again, or ask a shorter question.") from exc
        except httpx.TransportError as exc:
            # Connection problems (no internet, DNS, dropped connection): retry a little, then report.
            logger.warning("Could not reach Gemini on attempt %s (%s)", attempt, type(exc).__name__)
            backoff = _backoff_seconds(attempt)
            if attempt < max_attempts and (_monotonic() - started) + backoff < total_budget:
                _sleep(backoff)
                continue
            raise LLMError(503, "gemini_unreachable",
                           "Cannot reach Gemini right now. Check your internet connection and try again.") from exc


# ---------------------------------------------------------------- public API

def complete(
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    json_output: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
    time_budget: float | None = None,
) -> str:
    """Send a conversation to Gemini and return its reply text (retries, cooldown, cache and de-duplication)."""
    settings = get_settings()
    model = settings.gemini_model
    thinking = settings.gemini_thinking_level.strip().lower()
    key = _cache_key(model, system, messages, max_tokens, json_output, thinking)

    cached = _cache.get(key)
    if cached is not None:
        logger.info("Gemini answer served from cache (key %s)", key[:8])
        return cached

    is_leader, call = _singleflight_enter(key)
    if not is_leader:
        logger.info("Identical Gemini request already running; waiting for it (key %s)", key[:8])
        if not call.done.wait(settings.gemini_total_time_budget_seconds + 30):
            raise LLMError(504, "gemini_timeout", "Gemini did not finish the answer in time. Please try again.")
        if call.error is not None:
            raise call.error
        return call.value or ""

    try:
        _breaker.before_call()
        text = _complete_uncached(system, messages, max_tokens, json_output, model, max_attempts, time_budget)
    except LLMError as exc:
        if exc.code in TRANSIENT_CODES:
            _breaker.on_transient_failure()
        elif exc.code == "rate_limited":
            _breaker.on_quota_exhausted()
        _singleflight_leave(key, call, error=exc)
        raise
    except BaseException as exc:
        _singleflight_leave(key, call, error=exc)
        raise
    _breaker.on_success()
    _cache.put(key, text, settings.gemini_cache_ttl_seconds, settings.gemini_cache_max_entries)
    _singleflight_leave(key, call, value=text)
    return text


def _complete_uncached(system: str, messages: list[dict[str, Any]], max_tokens: int | None,
                       json_output: bool, model: str, max_attempts: int = MAX_ATTEMPTS,
                       time_budget: float | None = None) -> str:
    settings = get_settings()
    client = _get_client()
    started = _monotonic()
    contents = _to_contents(messages)

    def attempt(timeout_seconds: float) -> Any:
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens or settings.gemini_max_output_tokens,
            temperature=0.2,  # low randomness keeps answers close to the document
            response_mime_type="application/json" if json_output else "text/plain",
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
            thinking_config=_thinking_config(),
        )
        return client.models.generate_content(model=model, contents=contents, config=config)

    response, attempts, attempt_started = _with_retries(attempt, model, started, max_attempts, time_budget)
    _log_success(response, model, attempts, _monotonic() - attempt_started, _monotonic() - started)
    text = (response.text or "").strip()
    if not text:
        # Usually means the reply was blocked by a safety filter or hit the token limit.
        logger.warning("Gemini returned no text (finish reason may be safety or length)")
        raise LLMError(502, "empty_response", "Gemini returned an empty response. Please try again or rephrase the question.")
    return text


def stream_text(
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    json_output: bool = False,
) -> Iterator[str]:
    """
    Yield the reply as it is generated.

    - Errors before the first text are retried (as in complete) and raised as LLMError.
    - Errors after the first text are raised as LLMError too; the caller must report them.
    - If the caller stops reading (client disconnects), nothing is cached and no failure is counted.
    """
    settings = get_settings()
    model = settings.gemini_model
    thinking = settings.gemini_thinking_level.strip().lower()
    key = _cache_key(model, system, messages, max_tokens, json_output, thinking)

    cached = _cache.get(key)
    if cached is not None:
        logger.info("Gemini streamed answer served from cache (key %s)", key[:8])
        yield cached
        return

    _breaker.before_call()
    client = _get_client()
    started = _monotonic()
    contents = _to_contents(messages)

    def open_stream(timeout_seconds: float) -> tuple[str, Iterator[Any]]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens or settings.gemini_max_output_tokens,
            temperature=0.2,
            response_mime_type="application/json" if json_output else "text/plain",
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
            thinking_config=_thinking_config(),
        )
        iterator = iter(client.models.generate_content_stream(model=model, contents=contents, config=config))
        for chunk in iterator:  # wait for the first piece of text, so early errors can be retried
            text = chunk.text or ""
            if text:
                return text, iterator
        raise LLMError(502, "empty_response", "Gemini returned an empty response. Please try again or rephrase the question.")

    try:
        (first_text, iterator), attempts, _ = _with_retries(open_stream, model, started)
    except LLMError as exc:
        if exc.code in TRANSIENT_CODES:
            _breaker.on_transient_failure()
        elif exc.code == "rate_limited":
            _breaker.on_quota_exhausted()
        raise

    parts = [first_text]
    yield first_text
    try:
        for chunk in iterator:
            if _monotonic() - started > settings.gemini_total_time_budget_seconds:
                raise LLMError(504, "gemini_timeout", "Gemini did not finish the answer in time. Please try again.")
            text = chunk.text or ""
            if text:
                parts.append(text)
                yield text
    except LLMError as exc:
        if exc.code in TRANSIENT_CODES:
            _breaker.on_transient_failure()
        elif exc.code == "rate_limited":
            _breaker.on_quota_exhausted()
        raise
    except errors.APIError as exc:
        _breaker.on_transient_failure()
        logger.warning("Gemini stream failed after it started: HTTP %s", exc.code)
        raise LLMError(502, "stream_interrupted",
                       "The answer was interrupted while Gemini was writing it. Please try again.") from exc
    except (httpx.TransportError, TimeoutError) as exc:
        _breaker.on_transient_failure()
        logger.warning("Gemini stream connection interrupted (%s)", type(exc).__name__)
        raise LLMError(502, "stream_interrupted",
                       "The answer was interrupted while Gemini was writing it. Please try again.") from exc

    full = "".join(parts).strip()
    _breaker.on_success()
    _cache.put(key, full, settings.gemini_cache_ttl_seconds, settings.gemini_cache_max_entries)
    logger.info("Gemini stream finished: model=%s attempts=%d seconds=%.1f", model, attempts, _monotonic() - started)
