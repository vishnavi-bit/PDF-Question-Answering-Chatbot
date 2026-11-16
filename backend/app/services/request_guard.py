"""
Request guard: stops the same request from running twice at the same time, and returns
recent results for identical requests instead of creating duplicate records.

Used for chat questions (client_request_id) and study generation (same options and PDFs).
Keys must include everything that changes the result (PDF selection, counts, modes).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.config import get_settings

T = TypeVar("T")


class RequestInProgress(Exception):
    """The same request is already being processed. The client should wait, not resend."""


class _Pending:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.error: BaseException | None = None
        self.value: Any = None


class RequestGuard:
    def __init__(self, name: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self._clock = clock
        self._lock = threading.Lock()
        self._results: dict[str, tuple[float, Any]] = {}
        self._inflight: dict[str, _Pending] = {}

    @staticmethod
    def make_key(*parts: Any) -> str:
        """A stable key from the request's parts (dicts and lists are sorted first)."""
        text = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _purge(self, now: float) -> None:
        expired = [key for key, (expires, _) in self._results.items() if expires <= now]
        for key in expired:
            del self._results[key]

    def acquire(self, key: str) -> tuple[bool, Any]:
        """
        Returns (True, None) when the caller must do the work and then call complete() or abandon().
        Returns (False, value) when a recent identical request already finished.
        Raises RequestInProgress when an identical request is still running.
        """
        now = self._clock()
        with self._lock:
            self._purge(now)
            if key in self._results:
                return False, self._results[key][1]
            if key in self._inflight:
                raise RequestInProgress("This request is already being processed. Please wait a moment.")
            self._inflight[key] = _Pending()
            return True, None

    def complete(self, key: str, value: Any) -> None:
        ttl = get_settings().request_dedupe_ttl_seconds
        with self._lock:
            pending = self._inflight.pop(key, None)
            if ttl > 0:
                self._results[key] = (self._clock() + ttl, value)
        if pending is not None:
            pending.value = value
            pending.done.set()

    def abandon(self, key: str, error: BaseException | None = None) -> None:
        """The work failed: forget it so the client may retry. Failed results are never remembered."""
        with self._lock:
            pending = self._inflight.pop(key, None)
        if pending is not None:
            pending.error = error
            pending.done.set()

    def run(self, key: str, action: Callable[[], T], wait_seconds: float = 180.0) -> T:
        """Run action once for this key. A concurrent identical call waits for the same result."""
        now = self._clock()
        with self._lock:
            self._purge(now)
            if key in self._results:
                return self._results[key][1]
            pending = self._inflight.get(key)
            leader = pending is None
            if leader:
                pending = _Pending()
                self._inflight[key] = pending
        if not leader:
            if not pending.done.wait(wait_seconds):
                raise RequestInProgress("This request is still being processed. Please wait a moment.")
            if pending.error is not None:
                raise pending.error
            return pending.value
        try:
            value = action()
        except BaseException as exc:
            self.abandon(key, exc)
            raise
        self.complete(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._results.clear()
            self._inflight.clear()


# One guard per kind of request, so keys cannot collide between features.
chat_guard = RequestGuard("chat")
study_guard = RequestGuard("study")
