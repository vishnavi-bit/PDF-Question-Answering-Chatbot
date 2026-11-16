"""Study Assistant endpoints: notes, quizzes, flashcards, exam questions, topic explanations and progress."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.study_schema import (
    ExamRequest,
    ExamSetOut,
    ExplainOut,
    ExplainRequest,
    FlashcardProgressUpdate,
    FlashcardRequest,
    FlashcardSetOut,
    NotesOut,
    NotesRequest,
    ProgressOut,
    QuizRequest,
    QuizResult,
    QuizSetOut,
    QuizSubmit,
)
from app.services import study_progress_service as progress_service
from app.services import study_context, study_service
from app.services.request_guard import RequestGuard, study_guard
from app.services.llm_service import LLMError
from app.services.study_context import StudyError

router = APIRouter(prefix="/study", tags=["study assistant"])
T = TypeVar("T")


def _ready_ids(db: Session, document_ids: list[str]) -> list[str]:
    """The ready PDFs a request will use. Part of every request key, so new PDFs change the key."""
    return _call(lambda: sorted(document.id for document in study_context.ready_documents(db, document_ids)))


def _guarded(key_parts: tuple, action: Callable[[], T]) -> T:
    """Identical requests share one result for a short time (no duplicate records or Gemini calls)."""
    return study_guard.run(RequestGuard.make_key(*key_parts), action)


def _call(action: Callable[[], T]) -> T:
    """Turn service errors into HTTP errors with friendly messages (no stack traces)."""
    try:
        return action()
    except StudyError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/notes", response_model=NotesOut)
def create_notes(body: NotesRequest, db: Session = Depends(get_db)) -> NotesOut:
    ids = _ready_ids(db, body.document_ids)
    return _guarded(("notes", body.mode, ids), lambda: _call(lambda: study_service.generate_notes(db, body.document_ids, body.mode)))


@router.post("/quizzes", response_model=QuizSetOut, status_code=status.HTTP_201_CREATED)
def create_quiz(body: QuizRequest, db: Session = Depends(get_db)) -> QuizSetOut:
    ids = _ready_ids(db, body.document_ids)
    quiz_id = _guarded(("quiz", body.count, body.difficulty, ids), lambda: _call(lambda: study_service.generate_quiz(db, body.document_ids, body.count, body.difficulty).id))
    return _call(lambda: progress_service.get_quiz(db, quiz_id))


@router.get("/quizzes/{quiz_id}", response_model=QuizSetOut)
def read_quiz(quiz_id: int, db: Session = Depends(get_db)) -> QuizSetOut:
    return _call(lambda: progress_service.get_quiz(db, quiz_id))


@router.post("/quizzes/{quiz_id}/attempts", response_model=QuizResult, status_code=status.HTTP_201_CREATED)
def submit_quiz(quiz_id: int, body: QuizSubmit, db: Session = Depends(get_db)) -> QuizResult:
    return _call(lambda: progress_service.grade_quiz(db, quiz_id, body.answers))


@router.post("/flashcards", response_model=FlashcardSetOut, status_code=status.HTTP_201_CREATED)
def create_flashcards(body: FlashcardRequest, db: Session = Depends(get_db)) -> FlashcardSetOut:
    ids = _ready_ids(db, body.document_ids)
    deck_id = _guarded(("flashcards", body.count, ids), lambda: _call(lambda: study_service.generate_flashcards(db, body.document_ids, body.count).id))
    return _call(lambda: progress_service.get_flashcards(db, deck_id))


@router.get("/flashcards/{deck_id}", response_model=FlashcardSetOut)
def read_flashcards(deck_id: int, db: Session = Depends(get_db)) -> FlashcardSetOut:
    return _call(lambda: progress_service.get_flashcards(db, deck_id))


@router.put("/flashcards/{deck_id}/progress")
def update_flashcard_progress(deck_id: int, body: FlashcardProgressUpdate, db: Session = Depends(get_db)) -> dict:
    studied = _call(lambda: progress_service.set_flashcard_studied(db, deck_id, body.card_index, body.studied))
    return {"studied_indices": studied}


@router.post("/exams", response_model=ExamSetOut, status_code=status.HTTP_201_CREATED)
def create_exam(body: ExamRequest, db: Session = Depends(get_db)) -> dict:
    ids = _ready_ids(db, body.document_ids)
    exam_id = _guarded(("exam", body.short_count, body.long_count, ids),
                       lambda: _call(lambda: study_service.generate_exam(db, body.document_ids, body.short_count, body.long_count).id))
    return _call(lambda: progress_service.get_exam(db, exam_id))


@router.get("/exams/{exam_id}", response_model=ExamSetOut)
def read_exam(exam_id: int, db: Session = Depends(get_db)) -> dict:
    return _call(lambda: progress_service.get_exam(db, exam_id))


@router.post("/explain", response_model=ExplainOut)
def explain(body: ExplainRequest, db: Session = Depends(get_db)) -> ExplainOut:
    ids = _ready_ids(db, body.document_ids)
    return _guarded(("explain", body.topic.lower(), ids), lambda: _call(lambda: study_service.explain_topic(db, body)))


@router.get("/progress", response_model=ProgressOut)
def read_progress(db: Session = Depends(get_db)) -> ProgressOut:
    return progress_service.progress(db)
