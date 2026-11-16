"""
Conversation storage and the chat flow (saves questions and answers in SQLite).
"""

from __future__ import annotations

import json
import logging

from collections.abc import Iterator

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import Conversation, Document, Message
from app.schemas.chat_schema import ChatRequest, MessageOut, SourceCitation
from app.services import rag_service
from app.services.request_guard import RequestGuard, RequestInProgress, chat_guard
from app.services.llm_service import LLMError
from app.services.rag_service import IngestError

logger = logging.getLogger(__name__)

TITLE_LENGTH = 60


class ChatFlowError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

def list_conversations(db: Session, query: str | None = None) -> list[tuple[Conversation, int]]:
    """All conversations, newest first. With `query`, matches titles and message text (case-insensitive)."""
    statement = (
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
    )
    text = (query or "").strip()
    if text:
        matching_messages = select(Message.conversation_id).where(Message.content.contains(text, autoescape=True))
        statement = statement.where(
            or_(Conversation.title.contains(text, autoescape=True), Conversation.id.in_(matching_messages))
        )
    rows = db.execute(
        statement
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    ).all()
    return [(conversation, int(count)) for conversation, count in rows]


def get_conversation(db: Session, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ChatFlowError(404, "conversation_not_found", "Conversation not found.")
    return conversation


def rename_conversation(db: Session, conversation_id: int, title: str) -> Conversation:
    conversation = get_conversation(db, conversation_id)
    conversation.title = title[:120]
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation_id: int) -> None:
    conversation = get_conversation(db, conversation_id)
    db.delete(conversation)  # messages are removed by the cascade
    db.commit()


def set_feedback(db: Session, message_id: int, feedback: str | None) -> Message:
    message = db.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise ChatFlowError(404, "message_not_found", "Answer not found.")
    message.feedback = feedback
    db.commit()
    db.refresh(message)
    return message


def message_to_out(message: Message) -> MessageOut:
    sources: list[SourceCitation] = []
    if message.sources_json:
        try:
            sources = [SourceCitation.model_validate(item) for item in json.loads(message.sources_json)]
        except (ValueError, TypeError):
            logger.warning("Stored sources for message %s could not be read", message.id)
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        sources=sources,
        feedback=message.feedback,
        created_at=message.created_at,
    )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def _selected_documents(db: Session, document_ids: list[str]) -> list[str] | None:
    """Check the selected documents exist and are ready. Empty list = search all."""
    if not document_ids:
        return None
    unique_ids = list(dict.fromkeys(document_ids))
    documents = db.scalars(select(Document).where(Document.id.in_(unique_ids))).all()
    found = {document.id: document for document in documents}
    missing = [doc_id for doc_id in unique_ids if doc_id not in found]
    if missing:
        raise ChatFlowError(404, "document_not_found", "One or more selected documents were not found.")
    not_ready = [document.filename for document in documents if document.processing_status != "ready"]
    if not_ready:
        raise ChatFlowError(
            400,
            "document_not_ready",
            f"These documents are not ready for questions: {', '.join(not_ready)}. Remove them from the selection.",
        )
    return unique_ids


def _prepare_chat(db: Session, request: ChatRequest):
    question = rag_service.validate_question(request.question)
    document_ids = _selected_documents(db, request.document_ids)
    if request.conversation_id is not None:
        conversation = get_conversation(db, request.conversation_id)
        history_rows = db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
        ).all()
    else:
        conversation = None
        history_rows = []
    history = rag_service.history_from_messages(list(history_rows))
    return question, document_ids, conversation, history


def _save_exchange(db: Session, question: str, conversation: Conversation | None, result) -> dict:
    """Save the question and answer together, only after Gemini has answered."""
    if conversation is None:
        conversation = Conversation(title=question[:TITLE_LENGTH])
        db.add(conversation)
        db.flush()

    user_message = Message(conversation_id=conversation.id, role="user", content=question)
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.answer,
        sources_json=json.dumps([source.model_dump() for source in result.sources]),
    )
    db.add_all([user_message, assistant_message])
    conversation.updated_at = func.now()
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    db.refresh(conversation)
    return {
        "conversation_id": conversation.id,
        "user_message": message_to_out(user_message),
        "assistant_message": message_to_out(assistant_message),
        "answered_from_documents": result.answered_from_documents,
        "retrieval": result.retrieval,
    }


def _request_key(request: ChatRequest) -> str | None:
    if not request.client_request_id:
        return None
    return RequestGuard.make_key("chat", request.conversation_id, request.client_request_id)


def _guard_acquire(key: str) -> tuple[bool, dict | None]:
    try:
        return chat_guard.acquire(key)
    except RequestInProgress as exc:
        raise ChatFlowError(409, "request_in_progress", str(exc)) from exc


def _send(db: Session, request: ChatRequest) -> dict:
    try:
        question, document_ids, conversation, history = _prepare_chat(db, request)
        result = rag_service.answer_question(
            question=question,
            document_ids=document_ids,
            history=history,
            top_k=request.top_k,
            answer_style=request.answer_style,
        )
    except IngestError as exc:
        raise ChatFlowError(exc.status_code, "invalid_question", exc.message) from exc
    except LLMError as exc:
        raise ChatFlowError(exc.status_code, exc.code, exc.message) from exc
    return _save_exchange(db, question, conversation, result)


def send_message(db: Session, request: ChatRequest) -> dict:
    """
    Answer a question and store both messages.
    The question is only saved when Gemini answers, so a failed request can be retried cleanly.
    With client_request_id, a repeated request returns the first result instead of saving it twice.
    """
    key = _request_key(request)
    if key is None:
        return _send(db, request)
    fresh, stored = _guard_acquire(key)
    if not fresh:
        return stored
    try:
        payload = _send(db, request)
    except BaseException as exc:
        chat_guard.abandon(key, exc)
        raise
    chat_guard.complete(key, payload)
    return payload


def stream_message(db: Session, request: ChatRequest) -> Iterator[dict]:
    """
    Streaming chat. Yields events: meta (retrieval info), delta (text), done (saved messages).
    Nothing is saved unless the answer completes. If the client disconnects, nothing is saved.
    """
    key = _request_key(request)
    if key is not None:
        fresh, stored = _guard_acquire(key)
        if not fresh:
            yield {"event": "done", **stored}
            return

    completed = False
    try:
        try:
            question, document_ids, conversation, history = _prepare_chat(db, request)
            result = None
            for event in rag_service.stream_answer(
                question=question,
                document_ids=document_ids,
                history=history,
                top_k=request.top_k,
                answer_style=request.answer_style,
            ):
                if event["type"] == "meta":
                    yield {"event": "meta", "retrieval": event["retrieval"]}
                elif event["type"] == "delta":
                    yield {"event": "delta", "text": event["text"]}
                elif event["type"] == "result":
                    result = event["result"]
        except IngestError as exc:
            raise ChatFlowError(exc.status_code, "invalid_question", exc.message) from exc
        except LLMError as exc:
            raise ChatFlowError(exc.status_code, exc.code, exc.message) from exc

        payload = _save_exchange(db, question, conversation, result)
        completed = True
        if key is not None:
            chat_guard.complete(key, payload)
        yield {"event": "done", **payload}
    finally:
        if key is not None and not completed:
            chat_guard.abandon(key)


def regenerate_stream(db: Session, conversation_id: int, document_ids: list[str], top_k: int, answer_style: str) -> Iterator[dict]:
    """
    Answer the last question again. The old answer is replaced ONLY after the new one succeeds,
    so a failed regenerate keeps the original answer.
    """
    conversation = get_conversation(db, conversation_id)
    messages = list(
        db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)).all()
    )
    last_user = next((message for message in reversed(messages) if message.role == "user"), None)
    if last_user is None:
        raise ChatFlowError(400, "nothing_to_regenerate", "There is no question in this chat to answer again.")
    previous_answer = messages[-1] if messages[-1].role == "assistant" else None
    earlier = [message for message in messages if message.id < last_user.id]

    try:
        selected = _selected_documents(db, document_ids)
        history = rag_service.history_from_messages(earlier)
        result = None
        for event in rag_service.stream_answer(
            question=last_user.content,
            document_ids=selected,
            history=history,
            top_k=top_k,
            answer_style=answer_style,
        ):
            if event["type"] == "meta":
                yield {"event": "meta", "retrieval": event["retrieval"]}
            elif event["type"] == "delta":
                yield {"event": "delta", "text": event["text"]}
            elif event["type"] == "result":
                result = event["result"]
    except IngestError as exc:
        raise ChatFlowError(exc.status_code, "invalid_question", exc.message) from exc
    except LLMError as exc:
        raise ChatFlowError(exc.status_code, exc.code, exc.message) from exc

    new_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=result.answer,
        sources_json=json.dumps([source.model_dump() for source in result.sources]),
    )
    if previous_answer is not None:
        db.delete(previous_answer)
    db.add(new_message)
    conversation.updated_at = func.now()
    db.commit()
    db.refresh(new_message)
    db.refresh(last_user)
    yield {
        "event": "done",
        "conversation_id": conversation.id,
        "user_message": message_to_out(last_user),
        "assistant_message": message_to_out(new_message),
        "answered_from_documents": result.answered_from_documents,
        "retrieval": result.retrieval,
    }

