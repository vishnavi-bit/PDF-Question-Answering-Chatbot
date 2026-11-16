"""
Study progress: server-side quiz grading, saved attempts, topic accuracy and flashcard tracking.

Correct answers are stored with the quiz but are only returned after grading,
so a student cannot read them from the quiz page before answering.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import FlashcardStudy, QuizAttempt, StudySet
from app.schemas.study_schema import (
    AttemptOut,
    FlashcardDeckProgress,
    FlashcardOut,
    FlashcardSetOut,
    ProgressOut,
    QuizItemResult,
    QuizPublicQuestion,
    QuizResult,
    QuizSetOut,
    StudyCitation,
    TopicStat,
)
from app.services.study_context import StudyError

WEAK_TOPIC_ACCURACY = 60.0  # topics below this percentage are listed as needing practice


def _load_set(db: Session, study_set_id: int, kind: str) -> StudySet:
    study_set = db.get(StudySet, study_set_id)
    if study_set is None or study_set.kind != kind:
        raise StudyError(404, "study_set_not_found", f"This {kind} was not found.")
    return study_set


def _payload(study_set: StudySet) -> dict[str, Any]:
    return json.loads(study_set.payload_json)


def _document_ids(study_set: StudySet) -> list[str]:
    return json.loads(study_set.document_ids_json)


def _citations(raw: list[dict[str, Any]]) -> list[StudyCitation]:
    return [StudyCitation.model_validate(item) for item in raw]


# ---------------------------------------------------------------- quizzes

def get_quiz(db: Session, quiz_id: int) -> QuizSetOut:
    study_set = _load_set(db, quiz_id, "quiz")
    questions = _payload(study_set)["questions"]
    return QuizSetOut(
        id=study_set.id,
        title=study_set.title,
        document_ids=_document_ids(study_set),
        questions=[
            QuizPublicQuestion(index=index, question=q["question"], options=q["options"], topic=q["topic"])
            for index, q in enumerate(questions)
        ],
        created_at=study_set.created_at,
    )


def grade_quiz(db: Session, quiz_id: int, answers: list[int | None]) -> QuizResult:
    study_set = _load_set(db, quiz_id, "quiz")
    questions = _payload(study_set)["questions"]
    if len(answers) != len(questions):
        raise StudyError(422, "answer_count", f"This quiz has {len(questions)} questions, but {len(answers)} answers were sent.")

    items: list[QuizItemResult] = []
    stored: list[dict[str, Any]] = []
    correct_count = 0
    for index, (question, chosen) in enumerate(zip(questions, answers)):
        is_correct = chosen is not None and chosen == question["correct_index"]
        correct_count += int(is_correct)
        items.append(
            QuizItemResult(
                index=index,
                question=question["question"],
                options=question["options"],
                chosen=chosen,
                correct_index=question["correct_index"],
                is_correct=is_correct,
                explanation=question["explanation"],
                topic=question["topic"],
                sources=_citations(question["sources"]),
            )
        )
        stored.append({"index": index, "topic": question["topic"], "chosen": chosen,
                       "correct_index": question["correct_index"], "is_correct": is_correct})

    total = len(questions)
    percent = round(correct_count * 100 / total, 1)
    attempt = QuizAttempt(
        study_set_id=study_set.id,
        total=total,
        correct=correct_count,
        percent=percent,
        answers_json=json.dumps(stored),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return QuizResult(attempt_id=attempt.id, total=total, correct=correct_count, percent=percent, items=items)


# ---------------------------------------------------------------- flashcards

def get_flashcards(db: Session, deck_id: int) -> FlashcardSetOut:
    study_set = _load_set(db, deck_id, "flashcards")
    cards = _payload(study_set)["cards"]
    studied = sorted(
        db.scalars(select(FlashcardStudy.card_index).where(FlashcardStudy.study_set_id == deck_id)).all()
    )
    from app.services.revision_service import deck_review_map

    reviews = deck_review_map(db, deck_id)
    return FlashcardSetOut(
        id=study_set.id,
        title=study_set.title,
        document_ids=_document_ids(study_set),
        cards=[
            FlashcardOut(
                index=index, question=card["question"], answer=card["answer"], sources=_citations(card["sources"]),
                status=reviews[index].status if index in reviews else "new",
                due_date=reviews[index].due_date.isoformat() if index in reviews and reviews[index].due_date else None,
                interval_days=reviews[index].interval_days if index in reviews else 0,
                ease_factor=reviews[index].ease_factor if index in reviews else 2.5,
                repetitions=reviews[index].repetitions if index in reviews else 0,
            )
            for index, card in enumerate(cards)
        ],
        studied_indices=list(studied),
    )


def set_flashcard_studied(db: Session, deck_id: int, card_index: int, studied: bool) -> list[int]:
    study_set = _load_set(db, deck_id, "flashcards")
    if card_index >= len(_payload(study_set)["cards"]):
        raise StudyError(422, "card_index", "That flashcard does not exist in this deck.")
    existing = db.scalar(
        select(FlashcardStudy).where(FlashcardStudy.study_set_id == deck_id, FlashcardStudy.card_index == card_index)
    )
    if studied and existing is None:
        db.add(FlashcardStudy(study_set_id=deck_id, card_index=card_index))
    elif not studied and existing is not None:
        db.delete(existing)
    db.commit()
    return get_flashcards(db, deck_id).studied_indices


# ---------------------------------------------------------------- exam papers

def get_exam(db: Session, exam_id: int) -> dict[str, Any]:
    study_set = _load_set(db, exam_id, "exam")
    questions = _payload(study_set)["questions"]
    return {
        "id": study_set.id,
        "title": study_set.title,
        "document_ids": _document_ids(study_set),
        "questions": [
            {
                "index": index,
                "kind": q["kind"],
                "question": q["question"],
                "answer": q["answer"],
                "sources": _citations(q["sources"]),
                "topic": q.get("topic", "General"),
                "importance": q.get("importance", "medium"),
            }
            for index, q in enumerate(questions)
        ],
    }


# ---------------------------------------------------------------- progress overview

def _topic_stats(attempts: list[QuizAttempt]) -> list[TopicStat]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # topic -> [attempted, correct]
    for attempt in attempts:
        for item in json.loads(attempt.answers_json):
            counts[item["topic"]][0] += 1
            counts[item["topic"]][1] += int(item["is_correct"])
    stats = [
        TopicStat(topic=topic, attempted=attempted, correct=correct, accuracy=round(correct * 100 / attempted, 1))
        for topic, (attempted, correct) in counts.items()
    ]
    return sorted(stats, key=lambda stat: (stat.accuracy, -stat.attempted, stat.topic))


def progress(db: Session) -> ProgressOut:
    attempts = list(db.scalars(select(QuizAttempt).order_by(QuizAttempt.id.desc())).all())
    quiz_titles = {
        study_set.id: study_set.title
        for study_set in db.scalars(select(StudySet).where(StudySet.kind == "quiz")).all()
    }
    total_questions = sum(attempt.total for attempt in attempts)
    total_correct = sum(attempt.correct for attempt in attempts)
    topics = _topic_stats(attempts)

    decks: list[FlashcardDeckProgress] = []
    for deck in db.scalars(select(StudySet).where(StudySet.kind == "flashcards").order_by(StudySet.id)).all():
        studied = db.scalar(select(func.count(FlashcardStudy.id)).where(FlashcardStudy.study_set_id == deck.id)) or 0
        decks.append(
            FlashcardDeckProgress(id=deck.id, title=deck.title, total=len(_payload(deck)["cards"]), studied=studied)
        )

    return ProgressOut(
        total_attempts=len(attempts),
        questions_answered=total_questions,
        overall_accuracy=round(total_correct * 100 / total_questions, 1) if total_questions else None,
        attempts=[
            AttemptOut(
                id=attempt.id,
                quiz_id=attempt.study_set_id,
                quiz_title=quiz_titles.get(attempt.study_set_id, "Deleted quiz"),
                total=attempt.total,
                correct=attempt.correct,
                percent=attempt.percent,
                created_at=attempt.created_at,
            )
            for attempt in attempts
        ],
        topics=topics,
        weak_topics=[stat for stat in topics if stat.accuracy < WEAK_TOPIC_ACCURACY],
        flashcard_decks=decks,
    )
