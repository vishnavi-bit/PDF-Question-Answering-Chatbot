"""Pydantic schemas for the Study Assistant."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StudyCitation(BaseModel):
    source_id: str
    document_id: str
    filename: str
    page_number: int


# ---------------------------------------------------------------- requests

class _DocumentScope(BaseModel):
    document_ids: list[str] = Field(default_factory=list, description="Empty = all ready PDFs")


class NotesRequest(_DocumentScope):
    mode: Literal["overview", "chapters"] = "overview"


class QuizRequest(_DocumentScope):
    count: int = Field(default=5, ge=1, le=30, description="Any number from 1 to 30")
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class FlashcardRequest(_DocumentScope):
    count: Literal[5, 10, 20] = 10


class ExamRequest(_DocumentScope):
    short_count: int = Field(default=5, ge=0, le=10)
    long_count: int = Field(default=2, ge=0, le=5)

    @field_validator("long_count")
    @classmethod
    def at_least_one_question(cls, value: int, info) -> int:
        short = info.data.get("short_count", 0)
        if value == 0 and short == 0:
            raise ValueError("Ask for at least one short or long question")
        return value


class ExplainRequest(_DocumentScope):
    topic: str = Field(min_length=2, max_length=200)
    follow_up: str | None = Field(default=None, max_length=300, description="A follow-up question about the topic")

    @field_validator("topic")
    @classmethod
    def strip_topic(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Enter a topic of at least two characters")
        return cleaned


class QuizSubmit(BaseModel):
    answers: list[int | None] = Field(description="Chosen option index (0-3) for each question, or null")

    @field_validator("answers")
    @classmethod
    def valid_options(cls, value: list[int | None]) -> list[int | None]:
        for answer in value:
            if answer is not None and not 0 <= answer <= 3:
                raise ValueError("Each answer must be 0, 1, 2, 3 or null")
        return value


class FlashcardProgressUpdate(BaseModel):
    card_index: int = Field(ge=0)
    studied: bool = True


# ---------------------------------------------------------------- generated content (validated)

class GroundedPoint(BaseModel):
    text: str
    sources: list[StudyCitation]


class NotesOut(BaseModel):
    mode: Literal["overview", "chapters"]
    overview: str | None = None
    key_points: list[GroundedPoint] = Field(default_factory=list)
    definitions: list[dict] = Field(default_factory=list)          # term, meaning, sources
    simple_explanations: list[dict] = Field(default_factory=list)  # concept, explanation, sources
    chapters: list[dict] = Field(default_factory=list)             # title, summary, page_start, sources
    note: str | None = None


class QuizPublicQuestion(BaseModel):
    index: int
    question: str
    options: list[str]
    topic: str


class QuizSetOut(BaseModel):
    id: int
    title: str
    document_ids: list[str]
    questions: list[QuizPublicQuestion]
    created_at: datetime | None = None


class QuizItemResult(BaseModel):
    index: int
    question: str
    options: list[str]
    chosen: int | None
    correct_index: int
    is_correct: bool
    explanation: str
    topic: str
    sources: list[StudyCitation]


class QuizResult(BaseModel):
    attempt_id: int
    total: int
    correct: int
    percent: float
    items: list[QuizItemResult]


class FlashcardOut(BaseModel):
    index: int
    question: str
    answer: str
    sources: list[StudyCitation]
    status: str = "new"            # new | known | need_practice (Phase 4)
    due_date: str | None = None     # next review date (SM-2)
    interval_days: int = 0
    ease_factor: float = 2.5
    repetitions: int = 0


class FlashcardSetOut(BaseModel):
    id: int
    title: str
    document_ids: list[str]
    cards: list[FlashcardOut]
    studied_indices: list[int]


class ExamQuestionOut(BaseModel):
    index: int
    kind: Literal["short", "long"]
    question: str
    answer: str
    sources: list[StudyCitation]
    topic: str = "General"
    importance: Literal["high", "medium", "low"] = "medium"


class ExamSetOut(BaseModel):
    id: int
    title: str
    document_ids: list[str]
    questions: list[ExamQuestionOut]


class ExplainOut(BaseModel):
    topic: str
    found: bool
    explanation: str | None = None
    example: str | None = None
    key_terms: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    sources: list[StudyCitation] = Field(default_factory=list)
    message: str | None = None


# ---------------------------------------------------------------- progress

class AttemptOut(BaseModel):
    id: int
    quiz_id: int
    quiz_title: str
    total: int
    correct: int
    percent: float
    created_at: datetime | None = None


class TopicStat(BaseModel):
    topic: str
    attempted: int
    correct: int
    accuracy: float


class FlashcardDeckProgress(BaseModel):
    id: int
    title: str
    total: int
    studied: int


class ProgressOut(BaseModel):
    total_attempts: int
    questions_answered: int
    overall_accuracy: float | None
    attempts: list[AttemptOut]
    topics: list[TopicStat]
    weak_topics: list[TopicStat]
    flashcard_decks: list[FlashcardDeckProgress]
