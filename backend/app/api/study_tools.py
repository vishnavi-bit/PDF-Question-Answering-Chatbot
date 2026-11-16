"""Phase 4 study endpoints: saved notes, mock exams (timed), saved questions, spaced repetition, revision and the learning path."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services import revision_service, study_context, study_progress_service, study_tools_service
from app.services.study_context import StudyError

router = APIRouter(prefix="/study", tags=["study assistant"])


def _raise(exc: StudyError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# ---------------------------------------------------------------- request bodies

class NoteCreate(BaseModel):
    mode: Literal["overview", "chapter", "topic"] = "overview"
    length: Literal["short", "detailed"] = "detailed"
    topic: str | None = Field(default=None, max_length=200)
    document_ids: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: dict[str, Any] | None = None


class ExamCreate(BaseModel):
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    mcq_count: int = Field(default=10, ge=1, le=30)
    descriptive_count: int = Field(default=3, ge=0, le=10)
    duration_minutes: int = Field(default=30, ge=5, le=180)
    title: str | None = Field(default=None, max_length=200)
    document_ids: list[str] = Field(default_factory=list)


class ExamSubmit(BaseModel):
    answers: list[int | None] = Field(default_factory=list)
    descriptive: list[str] = Field(default_factory=list, max_length=10)
    auto_submitted: bool = False


class SavedQuestionCreate(BaseModel):
    kind: Literal["short", "long", "mcq"]
    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(default="", max_length=4000)
    sources: list[dict] = Field(default_factory=list)


class ReviewUpdate(BaseModel):
    card_index: int = Field(ge=0)
    status: Literal["known", "need_practice"]


class PlanCreate(BaseModel):
    deck_id: int


class PlanComplete(BaseModel):
    completed: bool = True


# ---------------------------------------------------------------- notes

@router.post("/notes/saved", status_code=status.HTTP_201_CREATED)
def create_saved_notes(body: NoteCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        note = study_tools_service.create_notes(db, body.mode, body.length, body.document_ids, body.topic)
    except StudyError as exc:
        _raise(exc)
    return study_tools_service.note_out(note)


@router.get("/notes")
def list_saved_notes(db: Session = Depends(get_db)) -> dict[str, Any]:
    notes = study_tools_service.list_notes(db)
    return {"notes": notes, "total": len(notes)}


@router.get("/notes/{note_id}")
def read_saved_notes(note_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.database.models import StudyNote

    note = db.get(StudyNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="These notes were not found.")
    return study_tools_service.note_out(note)


@router.put("/notes/{note_id}")
def update_saved_notes(note_id: int, body: NoteUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        note = study_tools_service.update_notes(db, note_id, body.title, body.body)
    except StudyError as exc:
        _raise(exc)
    return study_tools_service.note_out(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_saved_notes(note_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        study_tools_service.delete_notes(db, note_id)
    except StudyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- mock exams

@router.post("/mock-exams", status_code=status.HTTP_201_CREATED)
def create_mock_exam(body: ExamCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        exam = study_tools_service.generate_mock_exam(
            db, body.document_ids, body.difficulty, body.mcq_count, body.descriptive_count,
            body.duration_minutes, body.title,
        )
        return study_tools_service.exam_for_student(db, exam.id)
    except StudyError as exc:
        _raise(exc)


@router.get("/mock-exams/{exam_id}")
def read_mock_exam(exam_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return study_tools_service.exam_for_student(db, exam_id)
    except StudyError as exc:
        _raise(exc)


@router.delete("/mock-exams/{exam_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_mock_exam(exam_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        study_tools_service.delete_exam(db, exam_id)
    except StudyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mock-exams/{exam_id}/start", status_code=status.HTTP_201_CREATED)
def start_mock_exam(exam_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return study_tools_service.start_attempt(db, exam_id)
    except StudyError as exc:
        _raise(exc)


@router.post("/mock-exam-attempts/{attempt_id}/submit")
def submit_mock_exam(attempt_id: int, body: ExamSubmit, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return study_tools_service.submit_attempt(db, attempt_id, body.answers, body.descriptive, body.auto_submitted)
    except StudyError as exc:
        _raise(exc)


@router.get("/mock-exam-attempts/{attempt_id}")
def read_mock_exam_result(attempt_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return study_tools_service.attempt_result(db, attempt_id)
    except StudyError as exc:
        _raise(exc)


@router.get("/mock-exam-attempts")
def list_mock_exam_attempts(db: Session = Depends(get_db)) -> dict[str, Any]:
    attempts = study_tools_service.attempt_history(db)
    return {"attempts": attempts, "total": len(attempts)}


# ---------------------------------------------------------------- saved questions

@router.post("/saved-questions", status_code=status.HTTP_201_CREATED)
def save_question(body: SavedQuestionCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = study_tools_service.save_question(db, body.kind, body.question, body.answer, body.sources)
    except StudyError as exc:
        _raise(exc)
    return {"id": row.id, "kind": row.kind, "question": row.question, "answer": row.answer}


@router.get("/saved-questions")
def list_saved_questions(db: Session = Depends(get_db)) -> dict[str, Any]:
    questions = study_tools_service.list_saved_questions(db)
    return {"questions": questions, "total": len(questions)}


@router.delete("/saved-questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_saved_question(question_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        study_tools_service.delete_saved_question(db, question_id)
    except StudyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- spaced repetition and revision

@router.put("/flashcards/{deck_id}/review")
def review_flashcard(deck_id: int, body: ReviewUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        review = revision_service.record_review(db, deck_id, body.card_index, body.status)
    except StudyError as exc:
        _raise(exc)
    return {
        "card_index": review.card_index,
        "status": review.status,
        "ease_factor": review.ease_factor,
        "interval_days": review.interval_days,
        "repetitions": review.repetitions,
        "due_date": review.due_date.isoformat() if review.due_date else None,
    }


@router.get("/revision/today")
def revision_today(db: Session = Depends(get_db)) -> dict[str, Any]:
    return revision_service.today_summary(db)


@router.get("/revision/upcoming")
def revision_upcoming(days: int = Query(default=7, ge=1, le=60), db: Session = Depends(get_db)) -> dict[str, Any]:
    return revision_service.upcoming(db, days=days)


@router.post("/revision-plans", status_code=status.HTTP_201_CREATED)
def create_revision_plan(body: PlanCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        plans = revision_service.create_plan(db, body.deck_id)
    except StudyError as exc:
        _raise(exc)
    return {"tasks": [
        {"id": p.id, "deck_id": p.deck_id, "title": p.title, "due_date": p.due_date.isoformat(), "completed": p.completed}
        for p in plans
    ]}


@router.post("/revision-plans/{plan_id}/complete")
def complete_revision_task(plan_id: int, body: PlanComplete, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        plan = revision_service.set_plan_completed(db, plan_id, body.completed)
    except StudyError as exc:
        _raise(exc)
    return {"id": plan.id, "completed": plan.completed, "completed_at": plan.completed_at.isoformat() if plan.completed_at else None}


# ---------------------------------------------------------------- learning path

@router.get("/learning-path")
def read_learning_path(db: Session = Depends(get_db)) -> dict[str, Any]:
    return study_tools_service.learning_path(db)
