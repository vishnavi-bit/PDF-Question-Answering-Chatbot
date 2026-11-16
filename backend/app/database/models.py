"""
SQLAlchemy ORM models.

SQLite stores application data (documents, conversations, messages and
chunk text). ChromaDB stores the vector embeddings. Each chunk row keeps the
`vector_id` that links it to its vector in ChromaDB.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    # processing | ready | failed | needs_ocr | password_protected | empty | corrupt
    processing_status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    table_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")            # ruled tables indexed (Phase 7)
    pages_without_text: Mapped[int] = mapped_column(Integer, default=0, server_default="0")     # blank or image-only pages (Phase 7)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
        Index("ix_chunks_document_page", "document_id", "page_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    vector_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), index=True
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation", "conversation_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    # JSON list of source citations (only for assistant messages)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "up", "down" or NULL (no feedback yet)
    feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class StudySet(Base):
    """A saved study item set: a quiz, a flashcard deck or an exam paper."""

    __tablename__ = "study_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # quiz | flashcards | exam
    title: Mapped[str] = mapped_column(String(200))
    document_ids_json: Mapped[str] = mapped_column(Text)
    # Generated items, including correct answers and sources. Never sent to the browser before grading.
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    attempts: Mapped[list["QuizAttempt"]] = relationship(
        back_populates="study_set", cascade="all, delete-orphan", passive_deletes=True, order_by="QuizAttempt.id"
    )
    flashcard_studies: Mapped[list["FlashcardStudy"]] = relationship(
        back_populates="study_set", cascade="all, delete-orphan", passive_deletes=True
    )


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    study_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("study_sets.id", ondelete="CASCADE"), index=True
    )
    total: Mapped[int] = mapped_column(Integer)
    correct: Mapped[int] = mapped_column(Integer)
    percent: Mapped[float] = mapped_column(Float)
    # JSON list: topic, chosen option, correct option, is_correct for every question
    answers_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    study_set: Mapped[StudySet] = relationship(back_populates="attempts")


class FlashcardStudy(Base):
    __tablename__ = "flashcard_studies"
    __table_args__ = (UniqueConstraint("study_set_id", "card_index", name="uq_flashcard_study_card"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    study_set_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("study_sets.id", ondelete="CASCADE"), index=True
    )
    card_index: Mapped[int] = mapped_column(Integer)
    studied_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    study_set: Mapped[StudySet] = relationship(back_populates="flashcard_studies")


# ---------------------------------------------------------------- Phase 4-6 tables (added by migration 0002)

class StudyNote(Base):
    """A saved set of study notes (overview, chapter or topic), editable by the student."""

    __tablename__ = "study_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(16))        # overview | chapter | topic
    length: Mapped[str] = mapped_column(String(8))       # short | detailed
    document_ids_json: Mapped[str] = mapped_column(Text)
    body_json: Mapped[str] = mapped_column(Text)         # sections, with sources
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class MockExam(Base):
    __tablename__ = "mock_exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[str] = mapped_column(String(16))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    document_ids_json: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)      # questions, with answers and sources
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    attempts: Mapped[list["MockExamAttempt"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", passive_deletes=True, order_by="MockExamAttempt.id"
    )


class MockExamAttempt(Base):
    __tablename__ = "mock_exam_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(Integer, ForeignKey("mock_exams.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    total_mcq: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exam: Mapped[MockExam] = relationship(back_populates="attempts")


class FlashcardReview(Base):
    """SM-2 spaced-repetition state for one flashcard."""

    __tablename__ = "flashcard_reviews"
    __table_args__ = (UniqueConstraint("deck_id", "card_index", name="uq_flashcard_review_card"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(Integer, ForeignKey("study_sets.id", ondelete="CASCADE"), index=True)
    card_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="new")   # new | known | need_practice
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[object | None] = mapped_column(Date, nullable=True, index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RevisionPlan(Base):
    """One planned revision task for a flashcard deck, due on a date."""

    __tablename__ = "revision_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(Integer, ForeignKey("study_sets.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[object] = mapped_column(Date, index=True)
    day_offset: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MindMap(Base):
    __tablename__ = "mind_maps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    document_ids_json: Mapped[str] = mapped_column(Text)
    tree_json: Mapped[str] = mapped_column(Text)   # central topic, branches, subtopics, sources
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SavedQuestion(Base):
    """A question the student saved for revision (with its answer and sources)."""

    __tablename__ = "saved_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))    # short | long | mcq
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
