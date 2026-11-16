"""Chat endpoints: POST /api/chat (complete answer) and POST /api/chat/stream (text as it is written)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.chat_schema import ChatRequest, ChatResponse, RegenerateRequest
from app.services import chat_service
from app.services.chat_service import ChatFlowError
from app.services.llm_service import LLMError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    try:
        result = chat_service.send_message(db, body)
    except ChatFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return ChatResponse(**result)


def _jsonable(value: Any) -> Any:
    """Make pydantic models and other values JSON-safe."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def sse_event(name: str, data: dict[str, Any]) -> str:
    """One Server-Sent Event. The data is JSON on a single line, so it can be parsed safely."""
    return f"event: {name}\ndata: {json.dumps(_jsonable(data), ensure_ascii=False)}\n\n"


def _error_event(status: int, detail: str) -> str:
    return sse_event("error", {"status": status, "detail": detail})


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """
    Stream the answer. Errors that happen BEFORE the first text are returned as normal HTTP
    errors (for example 503 when Gemini is cooling down). Errors AFTER the text has started
    are sent as an `error` event, and nothing is saved.
    """
    return _stream_response(chat_service.stream_message(db, body))


@router.post("/chat/regenerate")
def chat_regenerate(body: RegenerateRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """Answer the last question again (streamed). The old answer is replaced only if the new one succeeds."""
    events = chat_service.regenerate_stream(db, body.conversation_id, body.document_ids, body.top_k, body.answer_style)
    return _stream_response(events)


def _stream_response(events) -> StreamingResponse:
    primed: list[dict[str, Any]] = []
    try:
        for event in events:
            primed.append(event)
            if event["event"] in ("delta", "done"):
                break
    except ChatFlowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    def body_iterator() -> Iterator[str]:
        try:
            for event in primed:
                yield _event_text(event)
            for event in events:
                yield _event_text(event)
        except ChatFlowError as exc:
            yield _error_event(exc.status_code, exc.message)
        except LLMError as exc:
            yield _error_event(exc.status_code, exc.message)
        except Exception:
            logger.exception("Unexpected error while streaming a chat answer")
            yield _error_event(500, "An internal server error occurred. Please try again.")

    return StreamingResponse(
        body_iterator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _event_text(event: dict[str, Any]) -> str:
    name = event["event"]
    payload = {key: value for key, value in event.items() if key != "event"}
    return sse_event(name, payload)
