"""
Phase 5 PDF exports (ReportLab): notes, quizzes, quiz results, flashcards, important questions,
mock exam papers, mock exam results, saved questions and mind maps.

Each export reads the same stored data the screens show. Every item keeps its source references
(filename and page). Text that Helvetica cannot draw is replaced with "?" so no boxes appear.
"""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any, Callable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, ListFlowable, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.database.models import MockExam, MockExamAttempt, QuizAttempt, SavedQuestion, StudyNote, StudySet
from app.services import mind_map_service, revision_service, study_tools_service
from app.services.study_context import StudyError

APP_NAME = "AI Study Assistant"
MARGIN = 2 * cm
OPTION_LETTERS = "ABCD"

_styles = getSampleStyleSheet()
TITLE = ParagraphStyle("ExportTitle", parent=_styles["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22,
                       alignment=TA_LEFT, spaceAfter=6, textColor=colors.HexColor("#1f2937"))
H2 = ParagraphStyle("ExportH2", parent=_styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16,
                    spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#1f2937"))
BODY = ParagraphStyle("ExportBody", parent=_styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14,
                      spaceAfter=4)
META = ParagraphStyle("ExportMeta", parent=BODY, fontSize=9, leading=12, textColor=colors.HexColor("#4b5563"))
SOURCE = ParagraphStyle("ExportSource", parent=META, fontSize=8.5, leading=11, leftIndent=12,
                        textColor=colors.HexColor("#374151"))
ANSWER = ParagraphStyle("ExportAnswer", parent=BODY, leftIndent=12, textColor=colors.HexColor("#065f46"))


def _text(value: Any) -> str:
    """Safe for Helvetica (Windows-1252) and for ReportLab's XML paragraph markup."""
    clean = str(value if value is not None else "").encode("cp1252", "replace").decode("cp1252")
    return escape(clean)


def _sources_line(sources: list[dict[str, Any]]) -> str | None:
    seen: list[str] = []
    for source in sources or []:
        label = f"{source.get('filename', 'PDF')}, page {source.get('page_number', '?')}"
        if label not in seen:
            seen.append(label)
    return ("Source: " + "; ".join(seen)) if seen else None


def _source_para(sources: list[dict[str, Any]]) -> list[Any]:
    line = _sources_line(sources)
    return [Paragraph(_text(line), SOURCE)] if line else []


def _options(options: list[str], chosen: int | None = None, correct: int | None = None) -> list[Any]:
    rows = []
    for index, option in enumerate(options):
        marker = ""
        if correct is not None and index == correct:
            marker = "  (correct)"
        elif chosen is not None and index == chosen:
            marker = "  (your answer)"
        letter = OPTION_LETTERS[index] if index < len(OPTION_LETTERS) else str(index + 1)
        rows.append(Paragraph(f"{letter}. {_text(option)}{_text(marker)}", BODY))
    return rows


def _build(title: str, subtitle: str, fill: Callable[[list[Any]], None]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
        title=title[:150], author=APP_NAME, subject=subtitle[:150],
    )
    story: list[Any] = [Paragraph(_text(title), TITLE)]
    if subtitle:
        story.append(Paragraph(_text(subtitle), META))
    story.append(Spacer(1, 6))
    fill(story)

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8.5)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(MARGIN, 1.1 * cm, _text(f"{APP_NAME} - exported {datetime.now():%Y-%m-%d %H:%M}"))
        canvas.drawRightString(A4[0] - MARGIN, 1.1 * cm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _numbered(items: list[list[Any]]) -> list[Any]:
    """Question blocks, each kept on one page where it fits."""
    out: list[Any] = []
    for block in items:
        out.append(KeepTogether(block))
        out.append(Spacer(1, 4))
    return out


def _question_block(number: int, question: str, lines: list[Any]) -> list[Any]:
    return [Paragraph(f"{number}. {_text(question)}", H2), *lines]


# ---------------------------------------------------------------- notes

def notes_pdf(note: dict[str, Any]) -> bytes:
    body = note.get("body") or {}

    def fill(story: list[Any]) -> None:
        if body.get("overview"):
            story += [Paragraph("Overview", H2), Paragraph(_text(body["overview"]), BODY)]
        if body.get("chapters"):
            story.append(Paragraph("Chapters", H2))
            for chapter in body["chapters"]:
                story.append(Paragraph(_text(chapter.get("title")), BODY))
                story.append(Paragraph(_text(chapter.get("summary")), BODY))
                story += _source_para(chapter.get("sources", []))
        if body.get("key_points"):
            story.append(Paragraph("Key points", H2))
            story.append(ListFlowable(
                [Paragraph(_text(p.get("text")), BODY) for p in body["key_points"]], bulletType="bullet", leftIndent=14))
            for point in body["key_points"]:
                story += _source_para(point.get("sources", []))
        if body.get("definitions"):
            story.append(Paragraph("Definitions", H2))
            for item in body["definitions"]:
                story.append(Paragraph(f"<b>{_text(item.get('term'))}</b>: {_text(item.get('meaning'))}", BODY))
                story += _source_para(item.get("sources", []))
        if body.get("simple_explanations"):
            story.append(Paragraph("Simple explanations", H2))
            for item in body["simple_explanations"]:
                story.append(Paragraph(f"<b>{_text(item.get('concept'))}</b>: {_text(item.get('explanation'))}", BODY))
                story += _source_para(item.get("sources", []))

    return _build(note.get("title") or "Study notes", f"Notes ({note.get('mode')}, {note.get('length')})", fill)


# ---------------------------------------------------------------- quizzes

def quiz_pdf(title: str, questions: list[dict[str, Any]], with_answers: bool) -> bytes:
    def fill(story: list[Any]) -> None:
        blocks = []
        for number, q in enumerate(questions, start=1):
            lines = _options(q["options"], correct=q["correct_index"] if with_answers else None)
            if with_answers and q.get("explanation"):
                lines.append(Paragraph(f"Explanation: {_text(q['explanation'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, q["question"], lines))
        story += _numbered(blocks)

    subtitle = f"{len(questions)} questions" + (" (with answer key)" if with_answers else "")
    return _build(title or "Quiz", subtitle, fill)


def quiz_attempt_pdf(title: str, attempt: dict[str, Any], questions: list[dict[str, Any]]) -> bytes:
    def fill(story: list[Any]) -> None:
        story.append(Paragraph(
            f"Score: {attempt['correct']} of {attempt['total']} ({attempt['percent']}%)", BODY))
        blocks = []
        for number, (q, item) in enumerate(zip(questions, attempt["items"]), start=1):
            status = "Correct" if item.get("is_correct") else "Not correct"
            lines = [Paragraph(f"Result: {status}", META)]
            lines += _options(q["options"], chosen=item.get("chosen"), correct=q["correct_index"])
            if q.get("explanation"):
                lines.append(Paragraph(f"Explanation: {_text(q['explanation'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, q["question"], lines))
        story += _numbered(blocks)

    return _build(f"Results: {title}", "Quiz result", fill)


# ---------------------------------------------------------------- flashcards

def flashcards_pdf(title: str, cards: list[dict[str, Any]]) -> bytes:
    def fill(story: list[Any]) -> None:
        blocks = []
        for number, card in enumerate(cards, start=1):
            status = card.get("status", "new").replace("_", " ")
            lines = [Paragraph(f"Answer: {_text(card['answer'])}", ANSWER), Paragraph(f"Status: {_text(status)}", META)]
            lines += _source_para(card.get("sources", []))
            blocks.append(_question_block(number, card["question"], lines))
        story += _numbered(blocks)

    return _build(title or "Flashcards", f"{len(cards)} flashcards", fill)


# ---------------------------------------------------------------- important questions and saved questions

def exam_pdf(title: str, questions: list[dict[str, Any]]) -> bytes:
    def fill(story: list[Any]) -> None:
        blocks = []
        for number, q in enumerate(questions, start=1):
            lines = []
            if q.get("answer"):
                lines.append(Paragraph(f"Model answer: {_text(q['answer'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, f"[{q.get('kind', 'question')}] {q['question']}", lines))
        story += _numbered(blocks)

    return _build(title or "Important questions", f"{len(questions)} questions", fill)


def saved_questions_pdf(questions: list[dict[str, Any]]) -> bytes:
    def fill(story: list[Any]) -> None:
        blocks = []
        for number, q in enumerate(questions, start=1):
            lines = []
            if q.get("answer"):
                lines.append(Paragraph(f"Answer: {_text(q['answer'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, q["question"], lines))
        story += _numbered(blocks)

    return _build("Saved questions", f"{len(questions)} saved for revision", fill)


# ---------------------------------------------------------------- mock exams

def mock_exam_pdf(title: str, exam: dict[str, Any], with_answers: bool) -> bytes:
    def fill(story: list[Any]) -> None:
        story.append(Paragraph(f"Time allowed: {exam['duration_minutes']} minutes. Difficulty: {_text(exam['difficulty'])}.", BODY))
        blocks = []
        for number, q in enumerate(exam["mcq"], start=1):
            lines = [Paragraph(f"Topic: {_text(q.get('topic'))}", META)]
            lines += _options(q["options"], correct=q["correct_index"] if with_answers else None)
            if with_answers and q.get("explanation"):
                lines.append(Paragraph(f"Explanation: {_text(q['explanation'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, q["question"], lines))
        story += _numbered(blocks)
        if exam.get("descriptive"):
            story.append(Paragraph("Descriptive questions", H2))
            desc_blocks = []
            for number, q in enumerate(exam["descriptive"], start=1):
                lines = []
                if with_answers and q.get("model_answer"):
                    lines.append(Paragraph(f"Model answer: {_text(q['model_answer'])}", ANSWER))
                lines += _source_para(q.get("sources", []))
                desc_blocks.append(_question_block(number, q["question"], lines))
            story += _numbered(desc_blocks)

    return _build(title or "Mock exam", f"{len(exam['mcq'])} multiple-choice, {len(exam.get('descriptive', []))} descriptive"
                  + (" (answer key)" if with_answers else ""), fill)


def mock_attempt_pdf(result: dict[str, Any]) -> bytes:
    def fill(story: list[Any]) -> None:
        story.append(Paragraph(
            f"Score: {result['correct']} of {result['total_mcq']} multiple-choice ({result['percent']}%)", BODY))
        if result.get("auto_submitted"):
            story.append(Paragraph("This exam was submitted automatically when the time ran out.", META))
        if result.get("late"):
            story.append(Paragraph("This answer sheet was submitted after the time limit.", META))
        blocks = []
        for number, q in enumerate(result["mcq"], start=1):
            status = "Correct" if q["is_correct"] else "Not correct"
            lines = [Paragraph(f"Result: {status}  |  Topic: {_text(q.get('topic'))}", META)]
            lines += _options(q["options"], chosen=q.get("chosen"), correct=q["correct_index"])
            if q.get("explanation"):
                lines.append(Paragraph(f"Explanation: {_text(q['explanation'])}", ANSWER))
            lines += _source_para(q.get("sources", []))
            blocks.append(_question_block(number, q["question"], lines))
        story += _numbered(blocks)
        if result.get("descriptive"):
            story.append(Paragraph("Descriptive answers", H2))
            story.append(Paragraph(_text(result.get("note", "")), META))
            desc_blocks = []
            for number, q in enumerate(result["descriptive"], start=1):
                lines = [Paragraph(f"Your answer: {_text(q.get('your_answer') or '(no answer)')}", BODY),
                         Paragraph(f"Model answer: {_text(q.get('model_answer'))}", ANSWER)]
                lines += _source_para(q.get("sources", []))
                desc_blocks.append(_question_block(number, q["question"], lines))
            story += _numbered(desc_blocks)

    return _build(f"Results: {result['exam_title']}", "Mock exam result", fill)


# ---------------------------------------------------------------- mind maps

def mind_map_pdf(mind_map: dict[str, Any]) -> bytes:
    tree = mind_map["tree"]

    def fill(story: list[Any]) -> None:
        story.append(Paragraph(f"Centre: {_text(tree.get('centre'))}", H2))
        for branch in tree.get("branches", []):
            story.append(Paragraph(f"<b>{_text(branch['label'])}</b>", BODY))
            story += _source_para(branch.get("sources", []))
            for child in branch.get("children", []):
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;- {_text(child['label'])}", BODY))
                for line in _source_para(child.get("sources", [])):
                    story.append(line)

    return _build(mind_map.get("title") or "Mind map", f"{mind_map.get('node_count', 0)} nodes, outline view", fill)


# ---------------------------------------------------------------- loading the saved data and exporting

def _load_set(db: Session, set_id: int, kind: str) -> StudySet:
    row = db.get(StudySet, set_id)
    if row is None or row.kind != kind:
        raise StudyError(404, "not_found", "This item was not found.")
    return row


def export(db: Session, kind: str, item_id: int | None = None) -> tuple[bytes, str]:
    """Return (pdf bytes, file name) for a saved item."""
    if kind == "notes":
        from app.services.study_tools_service import note_out

        note = db.get(StudyNote, item_id)
        if note is None:
            raise StudyError(404, "not_found", "These notes were not found.")
        return notes_pdf(note_out(note)), f"notes-{item_id}.pdf"

    if kind == "quiz":
        quiz = _load_set(db, item_id, "quiz")
        payload = json.loads(quiz.payload_json)["questions"]
        return quiz_pdf(quiz.title, payload, with_answers=True), f"quiz-{item_id}.pdf"

    if kind == "quiz-attempt":
        attempt = db.get(QuizAttempt, item_id)
        if attempt is None:
            raise StudyError(404, "not_found", "This quiz result was not found.")
        quiz = _load_set(db, attempt.study_set_id, "quiz")
        questions = json.loads(quiz.payload_json)["questions"]
        result = {"correct": attempt.correct, "total": attempt.total, "percent": attempt.percent,
                  "items": json.loads(attempt.answers_json)}
        return quiz_attempt_pdf(quiz.title, result, questions), f"quiz-result-{item_id}.pdf"

    if kind == "flashcards":
        deck = _load_set(db, item_id, "flashcards")
        reviews = revision_service.deck_review_map(db, item_id)
        cards = []
        for index, card in enumerate(json.loads(deck.payload_json)["cards"]):
            status = reviews[index].status if index in reviews else "new"
            cards.append({**card, "status": status})
        return flashcards_pdf(deck.title, cards), f"flashcards-{item_id}.pdf"

    if kind == "exam":
        paper = _load_set(db, item_id, "exam")
        return exam_pdf(paper.title, json.loads(paper.payload_json)["questions"]), f"important-questions-{item_id}.pdf"

    if kind == "saved-questions":
        rows = db.query(SavedQuestion).order_by(SavedQuestion.id.desc()).all()
        questions = [{"question": r.question, "answer": r.answer, "sources": json.loads(r.sources_json or "[]")} for r in rows]
        return saved_questions_pdf(questions), "saved-questions.pdf"

    if kind == "mock-exam":
        exam = db.get(MockExam, item_id)
        if exam is None:
            raise StudyError(404, "not_found", "This mock exam was not found.")
        payload = json.loads(exam.payload_json)
        data = {"duration_minutes": exam.duration_minutes, "difficulty": exam.difficulty,
                "mcq": payload["mcq"], "descriptive": payload["descriptive"]}
        return mock_exam_pdf(exam.title, data, with_answers=True), f"mock-exam-{item_id}.pdf"

    if kind == "mock-exam-attempt":
        attempt = db.get(MockExamAttempt, item_id)
        if attempt is None:
            raise StudyError(404, "not_found", "This mock exam result was not found.")
        if attempt.submitted_at is None:
            raise StudyError(409, "not_submitted", "Submit the mock exam before exporting its result.")
        exam = db.get(MockExam, attempt.exam_id)
        result = study_tools_service._result_payload(attempt, exam)
        return mock_attempt_pdf(result), f"mock-exam-result-{item_id}.pdf"

    if kind == "mind-map":
        mind_map = mind_map_service.get_mind_map(db, item_id)
        return mind_map_pdf(mind_map), f"mind-map-{item_id}.pdf"
    raise StudyError(404, "unknown_export", "This export type does not exist.")
