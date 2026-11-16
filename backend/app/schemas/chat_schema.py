"""Pydantic schemas for chat, citations, conversations and feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceCitation(BaseModel):
    source_id: str = Field(description="Label used in the answer, e.g. S1")
    document_id: str
    filename: str
    page_number: int
    relevant_text: str
    similarity: float


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    document_ids: list[str] = Field(default_factory=list, description="Empty = search all ready documents")
    top_k: int = Field(default=5, ge=1, le=20)
    answer_style: Literal["short", "detailed"] = "detailed"
    client_request_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional id chosen by the browser. A repeated request with the same id returns the first answer instead of saving it twice.",
    )

    @field_validator("question")
    @classmethod
    def strip_and_check_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question must not be empty")
        return cleaned


class RegenerateRequest(BaseModel):
    conversation_id: int
    document_ids: list[str] = Field(default_factory=list, description="Empty = search all ready documents")
    top_k: int = Field(default=5, ge=1, le=20)
    answer_style: Literal["short", "detailed"] = "detailed"


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    sources: list[SourceCitation] = Field(default_factory=list)
    feedback: str | None = None
    created_at: datetime | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    user_message: MessageOut
    assistant_message: MessageOut
    answered_from_documents: bool
    retrieval: dict = Field(default_factory=dict)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message_count: int = 0


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    conversations: list[ConversationOut]
    total: int


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Title must not be empty")
        return cleaned


class FeedbackRequest(BaseModel):
    feedback: Literal["up", "down"] | None = None
