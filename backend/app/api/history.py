"""Conversation history endpoints (list, open, rename, delete, feedback)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Message
from app.schemas.chat_schema import (
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
    ConversationRename,
    FeedbackRequest,
    MessageOut,
)
from app.services import chat_service
from app.services.chat_service import ChatFlowError

router = APIRouter(tags=["history"])


def _raise(exc: ChatFlowError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    q: str | None = Query(default=None, max_length=200, description="Search titles and messages"),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    rows = chat_service.list_conversations(db, q)
    items = [
        ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=count,
        )
        for conversation, count in rows
    ]
    return ConversationListResponse(conversations=items, total=len(items))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int, db: Session = Depends(get_db)) -> ConversationDetail:
    try:
        conversation = chat_service.get_conversation(db, conversation_id)
    except ChatFlowError as exc:
        _raise(exc)
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
    ).all()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(messages),
        messages=[chat_service.message_to_out(message) for message in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_conversation(conversation_id: int, body: ConversationRename, db: Session = Depends(get_db)) -> ConversationOut:
    try:
        conversation = chat_service.rename_conversation(db, conversation_id, body.title)
    except ChatFlowError as exc:
        _raise(exc)
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=len(conversation.messages),
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        chat_service.delete_conversation(db, conversation_id)
    except ChatFlowError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/messages/{message_id}/feedback", response_model=MessageOut)
def set_feedback(message_id: int, body: FeedbackRequest, db: Session = Depends(get_db)) -> MessageOut:
    try:
        message = chat_service.set_feedback(db, message_id, body.feedback)
    except ChatFlowError as exc:
        _raise(exc)
    return chat_service.message_to_out(message)
