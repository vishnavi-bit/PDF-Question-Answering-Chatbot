"""
Fake Gemini client for mock tests. It follows a script: each item is either a reply
(text or a list of streamed pieces) or an exception to raise. No network calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from google.genai import errors

from app.core.config import get_settings
from app.services import llm_service


def api_error(code: int, status: str = "UNAVAILABLE", message: str = "provider said no", headers=None) -> errors.APIError:
    response = SimpleNamespace(headers=headers or {})
    body = {"error": {"code": code, "message": message, "status": status}}
    if code >= 500:
        return errors.ServerError(code, body, response)
    return errors.ClientError(code, body, response)


class ScriptedClient:
    """
    script: list of items consumed in order by each request.
      - str                      -> a complete reply (generate_content) or one streamed piece per call
      - list[str | Exception]    -> for streaming: pieces yielded in order, with an exception allowed in between
      - Exception                -> raised when the request starts
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.complete_calls = 0
        self.stream_calls = 0
        self.timeouts: list[int | None] = []
        self.models = self

    def _next(self):
        if not self.script:
            raise AssertionError("ScriptedClient ran out of scripted responses")
        return self.script.pop(0)

    def generate_content(self, *, model, contents, config):
        self.complete_calls += 1
        self.timeouts.append(config.http_options.timeout if config.http_options else None)
        item = self._next()
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item, usage_metadata=None)

    def generate_content_stream(self, *, model, contents, config):
        self.stream_calls += 1
        self.timeouts.append(config.http_options.timeout if config.http_options else None)
        item = self._next()
        return _stream(item)


def _stream(item):
    if isinstance(item, Exception):
        raise item
    pieces = item if isinstance(item, list) else [item]
    for piece in pieces:
        if isinstance(piece, Exception):
            raise piece
        yield SimpleNamespace(text=piece)


def install(monkeypatch, script: list[Any]) -> ScriptedClient:
    """Use a scripted client for every Gemini call in this test."""
    client = ScriptedClient(script)
    monkeypatch.setattr(get_settings(), "gemini_api_key", "AIza-test-key-not-real")
    monkeypatch.setattr(llm_service, "_client", client)
    return client


class FakeClock:
    """Controls time for cooldown and cache expiry tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
