"""
Phase 4 study tools: saved notes, mock exams (with a timer), saved questions and the learning path.

Every generated item is grounded (see study_service): it must cite real excerpts from the selected PDFs.
Progress shown to the student is only what has been recorded. Nothing is invented.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MockExam, MockExamAttempt, SavedQuestion, StudyNote
from app.schemas.study_schema import StudyCitation
from app.services import study_context, study_progress_service, study_service
from app.services.revision_service import due_cards
from app.services.study_context import StudyError
from app.services.study_service import (
    STUDY_SYSTEM_PROMPT,
    _citation_dicts,
    _citations,
    _grounded,
    _Explanation,
    _Point,
    _Definition,
    _Simple,
    _QuizQuestion,
    _ask,
    _title,
    _tokens_for,
)

EXAM_GRACE_SECONDS = 30   # a submission this many seconds after the deadline is accepted but marked late
DIFFICULTY_LEVELS = ("easy", "medium", "hard")


# ---------------------------------------------------------------- notes

def _json(text: str, default: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _notes_body_from(result) -> dict[str, Any]:
    """Turn a NotesOut into the stored body (sections with their sources)."""
    return {
        "overview": result.overview,
        "key_points": [{"text": p.text, "sources": [c.model_dump() for c in p.sources]} for p in result.key_points],
        "definitions": [{"term": d["term"], "meaning": d["meaning"], "sources": d["sources"]} for d in result.definitions],
        "simple_explanations": [
            {"concept": s["concept"], "explanation": s["explanation"], "sources": s["sources"]} for s in result.simple_explanations
        ],
        "chapters": [
            {"title": c["title"], "summary": c["summary"], "page_start": c["page_start"], "sources": c["sources"]}
            for c in result.chapters
        ],
    }


def _topic_notes(db: Session, topic: str, document_ids: list[str], length: str) -> dict[str, Any]:
    excerpts = study_context.select_topic_excerpts(db, topic, document_ids)
    if not excerpts:
        raise StudyError(400, "topic_not_found", "The selected PDFs do not seem to mention this topic.")
    by_id = study_service.excerpt_map(excerpts)
    data = _ask(
        f"Make study notes about the topic \"{topic}\" for a student. "
        f"{study_service.LENGTH_GUIDE.get(length, study_service.LENGTH_GUIDE['detailed'])} "
        "Return: 'overview', 'key_points' (text, source_ids), 'definitions' (term, meaning, source_ids), "
        "'simple_explanations' (concept, explanation, source_ids). "
        'Output: {"overview": "...", "key_points": [{"text": "...", "source_ids": ["S1"]}], '
        '"definitions": [{"term": "...", "meaning": "...", "source_ids": ["S1"]}], '
        '"simple_explanations": [{"concept": "...", "explanation": "...", "source_ids": ["S1"]}]}',
        excerpts,
        4096,
    )
    overview = str(data.get("overview") or "").strip()
    key_points = [
        {"text": item.text.strip(), "sources": _citation_dicts(citations)}
        for item, citations in _grounded(data.get("key_points"), _Point, by_id)
    ]
    definitions = [
        {"term": item.term.strip(), "meaning": item.meaning.strip(), "sources": _citation_dicts(citations)}
        for item, citations in _grounded(data.get("definitions"), _Definition, by_id)
    ]
    simple = [
        {"concept": item.concept.strip(), "explanation": item.explanation.strip(), "sources": _citation_dicts(citations)}
        for item, citations in _grounded(data.get("simple_explanations"), _Simple, by_id)
    ]
    if not (overview or key_points or definitions or simple):
        raise StudyError(502, "no_grounded_items", "No grounded notes could be made about this topic.")
    return {
        "overview": overview or None,
        "key_points": key_points,
        "definitions": definitions,
        "simple_explanations": simple,
        "chapters": [],
    }


def create_notes(db: Session, mode: str, length: str, document_ids: list[str], topic: str | None = None) -> StudyNote:
    if mode not in ("overview", "chapter", "topic"):
        raise StudyError(422, "mode", "Choose overview, chapter or topic notes.")
    if length not in ("short", "detailed"):
        raise StudyError(422, "length", "Choose short or detailed notes.")
    documents = study_context.ready_documents(db, document_ids)
    names = ", ".join(doc.filename for doc in documents)[:150]
    if mode == "topic":
        if not topic or len(topic.strip()) < 2:
            raise StudyError(422, "topic", "Enter the topic for topic notes.")
        body = _topic_notes(db, topic.strip(), document_ids, length)
        title = f"Topic: {topic.strip()}"[:200]
    elif mode == "chapter":
        result = study_service.generate_notes(db, document_ids, "chapters", length)
        body = _notes_body_from(result)
        title = f"Chapter notes from {names}"[:200]
    else:
        result = study_service.generate_notes(db, document_ids, "overview", length)
        body = _notes_body_from(result)
        title = f"Overview notes from {names}"[:200]
    note = StudyNote(
        title=title,
        mode=mode,
        length=length,
        document_ids_json=json.dumps(sorted({doc.id for doc in documents})),
        body_json=json.dumps(body),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


class _NoteSource(BaseModel):
    source_id: str
    document_id: str
    filename: str
    page_number: int


class _NoteBody(BaseModel):
    overview: str | None = None
    key_points: list[dict] = Field(default_factory=list)
    definitions: list[dict] = Field(default_factory=list)
    simple_explanations: list[dict] = Field(default_factory=list)
    chapters: list[dict] = Field(default_factory=list)


def update_notes(db: Session, note_id: int, title: str | None, body: dict[str, Any] | None) -> StudyNote:
    """Edit the title and the text of saved notes. Sources cannot be invented here: each kept item must cite real sources."""
    note = db.get(StudyNote, note_id)
    if note is None:
        raise StudyError(404, "note_not_found", "These notes were not found.")
    if title is not None:
        cleaned = title.strip()
        if not cleaned:
            raise StudyError(422, "title", "Notes need a title.")
        note.title = cleaned[:200]
    if body is not None:
        try:
            checked = _NoteBody.model_validate(body)
        except ValidationError as exc:
            raise StudyError(422, "body", "The notes could not be saved: " + exc.errors()[0]["msg"]) from exc
        cleaned_body = checked.model_dump()
        for section in ("key_points", "definitions", "simple_explanations", "chapters"):
            for item in cleaned_body[section]:
                item["sources"] = [_NoteSource.model_validate(source).model_dump() for source in item.get("sources", [])]
                if not item["sources"]:
                    raise StudyError(422, "sources", "Every kept item must keep at least one source.")
        note.body_json = json.dumps(cleaned_body)
    db.commit()
    db.refresh(note)
    return note


def note_out(note: StudyNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "title": note.title,
        "mode": note.mode,
        "length": note.length,
        "document_ids": _json(note.document_ids_json, []),
        "body": _json(note.body_json, {}),
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


def list_notes(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(StudyNote).order_by(StudyNote.updated_at.desc(), StudyNote.id.desc())).all()
    return [
        {"id": n.id, "title": n.title, "mode": n.mode, "length": n.length,
         "created_at": n.created_at.isoformat() if n.created_at else None,
         "updated_at": n.updated_at.isoformat() if n.updated_at else None}
        for n in rows
    ]


def delete_notes(db: Session, note_id: int) -> None:
    note = db.get(StudyNote, note_id)
    if note is None:
        raise StudyError(404, "note_not_found", "These notes were not found.")
    db.delete(note)
    db.commit()


# ---------------------------------------------------------------- mock exams

class _Descriptive(BaseModel):
    question: str = Field(min_length=3)
    model_answer: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


def generate_mock_exam(db: Session, document_ids: list[str], difficulty: str, mcq_count: int,
                       descriptive_count: int, duration_minutes: int, title: str | None = None) -> MockExam:
    if difficulty not in DIFFICULTY_LEVELS:
        raise StudyError(422, "difficulty", "Choose easy, medium or hard.")
    excerpts = study_context.select_study_excerpts(db, document_ids)
    by_id = study_service.excerpt_map(excerpts)
    guide = study_service.DIFFICULTY_GUIDE[difficulty]
    data = _ask(
        f"Create a mock exam: exactly {mcq_count} multiple-choice questions (4 different options, one correct, "
        f"'correct_index' 0 to 3, 'explanation', 'topic', 'source_ids') and exactly {descriptive_count} "
        "descriptive questions (question, model_answer of 3 to 6 sentences, source_ids). "
        f"Difficulty: {difficulty}. {guide} Every answer must come from the excerpts. "
        'Output: {"mcq": [{"question": "...", "options": ["...","...","...","..."], "correct_index": 0, '
        '"explanation": "...", "topic": "...", "source_ids": ["S1"]}], '
        '"descriptive": [{"question": "...", "model_answer": "...", "source_ids": ["S1"]}]}',
        excerpts,
        _tokens_for(mcq_count + descriptive_count * 2),
    )
    mcq = [
        {"question": item.question.strip(), "options": [o.strip() for o in item.options], "correct_index": item.correct_index,
         "explanation": item.explanation.strip(), "topic": item.topic.strip() or "General", "sources": _citation_dicts(citations)}
        for item, citations in _grounded(data.get("mcq"), _QuizQuestion, by_id)[:mcq_count]
    ]
    descriptive = [
        {"question": item.question.strip(), "model_answer": item.model_answer.strip(), "sources": _citation_dicts(citations)}
        for item, citations in _grounded(data.get("descriptive"), _Descriptive, by_id)[:descriptive_count]
    ]
    if not mcq and not descriptive:
        raise StudyError(502, "no_grounded_items", "No grounded exam questions could be made from these PDFs.")
    documents = study_context.ready_documents(db, document_ids)
    exam = MockExam(
        title=(title or f"Mock exam ({difficulty}): {len(mcq)} multiple-choice, {len(descriptive)} descriptive")[:200],
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        document_ids_json=json.dumps(sorted({doc.id for doc in documents})),
        payload_json=json.dumps({"mcq": mcq, "descriptive": descriptive}),
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def exam_for_student(db: Session, exam_id: int) -> dict[str, Any]:
    """The paper without answers, explanations or model answers."""
    exam = db.get(MockExam, exam_id)
    if exam is None:
        raise StudyError(404, "exam_not_found", "This mock exam was not found.")
    payload = _json(exam.payload_json, {"mcq": [], "descriptive": []})
    return {
        "id": exam.id,
        "title": exam.title,
        "difficulty": exam.difficulty,
        "duration_minutes": exam.duration_minutes,
        "mcq": [
            {"index": i, "question": q["question"], "options": q["options"], "topic": q["topic"]}
            for i, q in enumerate(payload["mcq"])
        ],
        "descriptive": [{"index": i, "question": q["question"]} for i, q in enumerate(payload["descriptive"])],
    }


def start_attempt(db: Session, exam_id: int) -> dict[str, Any]:
    exam = db.get(MockExam, exam_id)
    if exam is None:
        raise StudyError(404, "exam_not_found", "This mock exam was not found.")
    started = datetime.now()
    deadline = started + timedelta(minutes=exam.duration_minutes)
    attempt = MockExamAttempt(exam_id=exam.id, started_at=started, deadline=deadline, answers_json="{}")
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return {
        "attempt_id": attempt.id,
        "exam_id": exam.id,
        "started_at": started.isoformat(),
        "deadline": deadline.isoformat(),
        "duration_seconds": exam.duration_minutes * 60,
    }


def _result_payload(attempt: MockExamAttempt, exam: MockExam) -> dict[str, Any]:
    payload = _json(exam.payload_json, {"mcq": [], "descriptive": []})
    stored = _json(attempt.answers_json, {})
    chosen = stored.get("mcq", [])
    mcq_items = []
    for index, question in enumerate(payload["mcq"]):
        answer = chosen[index] if index < len(chosen) else None
        mcq_items.append({
            "index": index,
            "question": question["question"],
            "options": question["options"],
            "topic": question["topic"],
            "chosen": answer,
            "correct_index": question["correct_index"],
            "is_correct": answer is not None and answer == question["correct_index"],
            "explanation": question["explanation"],
            "sources": question["sources"],
        })
    descriptive_items = []
    written = stored.get("descriptive", [])
    for index, question in enumerate(payload["descriptive"]):
        descriptive_items.append({
            "index": index,
            "question": question["question"],
            "your_answer": written[index] if index < len(written) else "",
            "model_answer": question["model_answer"],
            "sources": question["sources"],
        })
    return {
        "attempt_id": attempt.id,
        "exam_id": exam.id,
        "exam_title": exam.title,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "auto_submitted": attempt.auto_submitted,
        "late": attempt.late,
        "total_mcq": attempt.total_mcq,
        "correct": attempt.correct,
        "percent": attempt.percent,
        "mcq": mcq_items,
        "descriptive": descriptive_items,
        "note": "Descriptive answers are compared with the model answer by you. They are not scored automatically.",
    }


def submit_attempt(db: Session, attempt_id: int, mcq_answers: list[int | None], descriptive_answers: list[str],
                   auto_submitted: bool) -> dict[str, Any]:
    attempt = db.get(MockExamAttempt, attempt_id)
    if attempt is None:
        raise StudyError(404, "attempt_not_found", "This exam attempt was not found.")
    if attempt.submitted_at is not None:
        raise StudyError(409, "already_submitted", "This exam has already been submitted.")
    exam = db.get(MockExam, attempt.exam_id)
    payload = _json(exam.payload_json, {"mcq": [], "descriptive": []})
    if len(mcq_answers) != len(payload["mcq"]):
        raise StudyError(422, "answer_count", f"This exam has {len(payload['mcq'])} multiple-choice questions, "
                                              f"but {len(mcq_answers)} answers were sent.")
    now = datetime.now()
    correct = sum(1 for given, question in zip(mcq_answers, payload["mcq"])
                  if given is not None and given == question["correct_index"])
    total = len(payload["mcq"])
    attempt.submitted_at = now
    attempt.auto_submitted = bool(auto_submitted)
    attempt.late = now > attempt.deadline + timedelta(seconds=EXAM_GRACE_SECONDS)
    attempt.total_mcq = total
    attempt.correct = correct
    attempt.percent = round(correct * 100 / total, 1) if total else None
    attempt.answers_json = json.dumps({
        "mcq": mcq_answers,
        "descriptive": [str(text)[:4000] for text in descriptive_answers[: len(payload["descriptive"])]],
    })
    db.commit()
    db.refresh(attempt)
    return _result_payload(attempt, exam)


def attempt_result(db: Session, attempt_id: int) -> dict[str, Any]:
    attempt = db.get(MockExamAttempt, attempt_id)
    if attempt is None:
        raise StudyError(404, "attempt_not_found", "This exam attempt was not found.")
    if attempt.submitted_at is None:
        raise StudyError(409, "not_submitted", "This exam has not been submitted yet.")
    return _result_payload(attempt, db.get(MockExam, attempt.exam_id))


def attempt_history(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(MockExamAttempt, MockExam).join(MockExam, MockExam.id == MockExamAttempt.exam_id)
        .order_by(MockExamAttempt.id.desc())
    ).all()
    return [
        {
            "attempt_id": attempt.id,
            "exam_id": exam.id,
            "exam_title": exam.title,
            "difficulty": exam.difficulty,
            "submitted": attempt.submitted_at is not None,
            "percent": attempt.percent,
            "correct": attempt.correct,
            "total_mcq": attempt.total_mcq,
            "auto_submitted": attempt.auto_submitted,
            "late": attempt.late,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        }
        for attempt, exam in rows
    ]


def delete_exam(db: Session, exam_id: int) -> None:
    exam = db.get(MockExam, exam_id)
    if exam is None:
        raise StudyError(404, "exam_not_found", "This mock exam was not found.")
    db.delete(exam)
    db.commit()


# ---------------------------------------------------------------- saved questions

def save_question(db: Session, kind: str, question: str, answer: str, sources: list[dict]) -> SavedQuestion:
    if kind not in ("short", "long", "mcq"):
        raise StudyError(422, "kind", "Kind must be short, long or mcq.")
    if not question.strip():
        raise StudyError(422, "question", "Enter the question to save.")
    saved = SavedQuestion(kind=kind, question=question.strip()[:2000], answer=answer.strip()[:4000],
                          sources_json=json.dumps([StudyCitation.model_validate(s).model_dump() for s in sources]))
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def list_saved_questions(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(SavedQuestion).order_by(SavedQuestion.id.desc())).all()
    return [
        {"id": row.id, "kind": row.kind, "question": row.question, "answer": row.answer,
         "sources": _json(row.sources_json, []), "created_at": row.created_at.isoformat() if row.created_at else None}
        for row in rows
    ]


def delete_saved_question(db: Session, question_id: int) -> None:
    row = db.get(SavedQuestion, question_id)
    if row is None:
        raise StudyError(404, "question_not_found", "This saved question was not found.")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------- learning path (only recorded data)

def learning_path(db: Session) -> dict[str, Any]:
    progress = study_progress_service.progress(db)
    cards_due = due_cards(db)
    ready_documents = study_context.ready_documents(db, []) if _has_documents(db) else []
    exam_attempts = db.scalar(select(MockExamAttempt.id).limit(1))
    steps: list[dict[str, Any]] = []
    has_quiz_data = progress.total_attempts > 0

    if not ready_documents:
        steps.append({"type": "upload", "title": "Upload a PDF to start",
                      "detail": "Your learning plan is built from your own PDFs and your quiz results.", "action": "documents"})
    if not has_quiz_data:
        steps.append({"type": "start", "title": "Take a quiz to find your weak topics",
                      "detail": "There is no quiz data yet, so no weak topics can be identified.", "action": "quiz"})
    for topic in progress.weak_topics[:5]:
        steps.append({
            "type": "practise",
            "title": f"Practise: {topic.topic}",
            "detail": f"You answered {topic.accuracy}% of the {topic.topic} questions correctly ({topic.correct} of {topic.attempted}). "
                      "Read notes on this topic, then take another quiz.",
            "action": "notes",
        })
    if cards_due:
        steps.append({"type": "revise", "title": f"Review {len(cards_due)} flashcard(s) due now",
                      "detail": "Spaced repetition works best when due cards are reviewed on time.", "action": "revision"})
    if has_quiz_data and not progress.weak_topics:
        steps.append({"type": "keep_going", "title": "No weak topics in your quiz results",
                      "detail": "Keep practising with a mock exam to check your readiness.", "action": "mock"})
    if exam_attempts is None and ready_documents:
        steps.append({"type": "exam", "title": "Try a timed mock exam",
                      "detail": "A timed mock exam shows how you perform under exam conditions.", "action": "mock"})

    return {
        "has_quiz_data": has_quiz_data,
        "quiz_attempts": progress.total_attempts,
        "questions_answered": progress.questions_answered,
        "overall_accuracy": progress.overall_accuracy,
        "weak_topics": [topic.model_dump() for topic in progress.weak_topics],
        "due_cards": len(cards_due),
        "steps": steps,
        "note": "This plan uses only the quiz results and revision data recorded in this app.",
    }


def _has_documents(db: Session) -> bool:
    from app.database.models import Document

    return db.scalar(select(Document.id).where(Document.processing_status == "ready").limit(1)) is not None
