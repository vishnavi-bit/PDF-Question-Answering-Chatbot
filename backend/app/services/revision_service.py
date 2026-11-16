"""
Spaced repetition (SM-2) for flashcards, plus revision plans and "what to revise today".

SM-2 in plain English
- Each card has an ease factor (how easy it is for you) and an interval (days until next review).
- "Known" is treated as a good answer; "Need practice" is treated as a failed answer.
- A good answer makes the interval longer: 1 day, then 6 days, then interval x ease.
- A failed answer starts the card again: review again tomorrow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import FlashcardReview, RevisionPlan, StudySet
from app.services.study_context import StudyError

MIN_EASE = 1.3
QUALITY_KNOWN = 4          # "Known": a correct answer with some hesitation
QUALITY_NEED_PRACTICE = 2  # "Need practice": treated as a failed review
REVISION_OFFSETS = (1, 3, 7, 14)  # days after a plan is made


@dataclass
class SM2State:
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0


def sm2_next(state: SM2State, quality: int) -> SM2State:
    """The next state after one review. quality: 0 (blackout) to 5 (perfect)."""
    if not 0 <= quality <= 5:
        raise ValueError("quality must be between 0 and 5")
    ease = state.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ease = max(MIN_EASE, ease)
    if quality < 3:
        return SM2State(ease_factor=ease, interval_days=1, repetitions=0)
    repetitions = state.repetitions + 1
    if repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = max(1, round(state.interval_days * ease))
    return SM2State(ease_factor=round(ease, 4), interval_days=interval, repetitions=repetitions)


def _quality_for(status: str) -> int:
    if status == "known":
        return QUALITY_KNOWN
    if status == "need_practice":
        return QUALITY_NEED_PRACTICE
    raise ValueError("status must be 'known' or 'need_practice'")


def _deck(db: Session, deck_id: int) -> StudySet:
    deck = db.get(StudySet, deck_id)
    if deck is None or deck.kind != "flashcards":
        raise StudyError(404, "deck_not_found", "This flashcard deck was not found.")
    return deck


def record_review(db: Session, deck_id: int, card_index: int, status: str, today: date | None = None) -> FlashcardReview:
    """Save a Known / Need practice answer and schedule the next review (SM-2)."""
    deck = _deck(db, deck_id)
    if card_index < 0 or card_index >= len(_deck_cards(deck)):
        raise StudyError(422, "card_index", "That flashcard does not exist in this deck.")
    today = today or date.today()
    review = db.scalar(select(FlashcardReview).where(FlashcardReview.deck_id == deck_id, FlashcardReview.card_index == card_index))
    if review is None:
        review = FlashcardReview(deck_id=deck_id, card_index=card_index, ease_factor=2.5,
                                 interval_days=0, repetitions=0, status="new")
        db.add(review)
    current = SM2State(review.ease_factor, review.interval_days, review.repetitions)
    nxt = sm2_next(current, _quality_for(status))
    review.ease_factor = nxt.ease_factor
    review.interval_days = nxt.interval_days
    review.repetitions = nxt.repetitions
    review.status = status
    review.due_date = today + timedelta(days=nxt.interval_days)
    review.last_reviewed_at = datetime.now()
    db.commit()
    db.refresh(review)
    return review


def _deck_cards(deck: StudySet) -> list:
    import json

    return json.loads(deck.payload_json)["cards"]


def deck_review_map(db: Session, deck_id: int) -> dict[int, FlashcardReview]:
    rows = db.scalars(select(FlashcardReview).where(FlashcardReview.deck_id == deck_id)).all()
    return {row.card_index: row for row in rows}


def due_cards(db: Session, today: date | None = None, within_days: int = 0) -> list[dict]:
    """Cards whose review date is today (or within `within_days` days), across all decks."""
    today = today or date.today()
    limit = today + timedelta(days=within_days)
    rows = db.execute(
        select(FlashcardReview, StudySet)
        .join(StudySet, StudySet.id == FlashcardReview.deck_id)
        .where(FlashcardReview.due_date.is_not(None), FlashcardReview.due_date <= limit)
        .order_by(FlashcardReview.due_date, FlashcardReview.deck_id, FlashcardReview.card_index)
    ).all()
    import json

    items = []
    for review, deck in rows:
        cards = json.loads(deck.payload_json)["cards"]
        if review.card_index < len(cards):
            items.append({
                "deck_id": deck.id,
                "deck_title": deck.title,
                "card_index": review.card_index,
                "question": cards[review.card_index]["question"],
                "due_date": review.due_date.isoformat(),
                "overdue": review.due_date < today,
            })
    return items


def create_plan(db: Session, deck_id: int, today: date | None = None) -> list[RevisionPlan]:
    """A revision plan for a deck: tasks on day 1, 3, 7 and 14 after today."""
    deck = _deck(db, deck_id)
    today = today or date.today()
    plans = []
    for offset in REVISION_OFFSETS:
        plan = RevisionPlan(
            deck_id=deck.id,
            title=f"Revise: {deck.title} (day {offset})",
            due_date=today + timedelta(days=offset),
            day_offset=offset,
            completed=False,
        )
        db.add(plan)
        plans.append(plan)
    db.commit()
    for plan in plans:
        db.refresh(plan)
    return plans


def set_plan_completed(db: Session, plan_id: int, completed: bool) -> RevisionPlan:
    plan = db.get(RevisionPlan, plan_id)
    if plan is None:
        raise StudyError(404, "plan_not_found", "This revision task was not found.")
    plan.completed = completed
    plan.completed_at = datetime.now() if completed else None
    db.commit()
    db.refresh(plan)
    return plan


def today_summary(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    tasks = db.scalars(
        select(RevisionPlan).where(RevisionPlan.due_date <= today).order_by(RevisionPlan.due_date, RevisionPlan.id)
    ).all()
    open_tasks = [task for task in tasks if not task.completed]
    cards = due_cards(db, today=today)
    return {
        "date": today.isoformat(),
        "tasks": [
            {"id": task.id, "deck_id": task.deck_id, "title": task.title, "due_date": task.due_date.isoformat(),
             "completed": task.completed, "overdue": task.due_date < today}
            for task in tasks
        ],
        "cards": cards,
        "open_task_count": len(open_tasks),
        "due_card_count": len(cards),
    }


def upcoming(db: Session, days: int = 7, today: date | None = None) -> dict:
    today = today or date.today()
    limit = today + timedelta(days=days)
    tasks = db.scalars(
        select(RevisionPlan).where(RevisionPlan.due_date > today, RevisionPlan.due_date <= limit).order_by(RevisionPlan.due_date)
    ).all()
    return {
        "from": today.isoformat(),
        "to": limit.isoformat(),
        "tasks": [
            {"id": task.id, "deck_id": task.deck_id, "title": task.title, "due_date": task.due_date.isoformat(), "completed": task.completed}
            for task in tasks
        ],
        "cards": due_cards(db, today=today, within_days=days)[:50],
    }
