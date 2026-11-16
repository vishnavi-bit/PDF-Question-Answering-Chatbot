"""Phase 5 endpoints: mind maps (grounded, saved) and PDF exports of saved study items."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.services import mind_map_service, pdf_export_service
from app.services.study_context import StudyError

router = APIRouter(prefix="/study", tags=["study exports and mind maps"])

ExportKind = Literal["notes", "quiz", "quiz-attempt", "flashcards", "exam", "saved-questions",
                     "mock-exam", "mock-exam-attempt", "mind-map"]


class MindMapCreate(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


class MindMapRename(BaseModel):
    title: str = Field(min_length=2, max_length=200)


def _raise(exc: StudyError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/mind-maps", status_code=status.HTTP_201_CREATED)
def create_mind_map(body: MindMapCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        mind_map = mind_map_service.generate_mind_map(db, body.document_ids)
    except StudyError as exc:
        _raise(exc)
    return mind_map_service.get_mind_map(db, mind_map.id)


@router.get("/mind-maps")
def list_mind_maps(db: Session = Depends(get_db)) -> dict[str, Any]:
    maps = mind_map_service.list_mind_maps(db)
    return {"mind_maps": maps, "total": len(maps)}


@router.get("/mind-maps/{map_id}")
def read_mind_map(map_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return mind_map_service.get_mind_map(db, map_id)
    except StudyError as exc:
        _raise(exc)


@router.put("/mind-maps/{map_id}")
def rename_mind_map(map_id: int, body: MindMapRename, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return mind_map_service.rename_mind_map(db, map_id, body.title)
    except StudyError as exc:
        _raise(exc)


@router.delete("/mind-maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_mind_map(map_id: int, db: Session = Depends(get_db)) -> Response:
    try:
        mind_map_service.delete_mind_map(db, map_id)
    except StudyError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export/saved-questions.pdf")
def export_saved_questions(db: Session = Depends(get_db)) -> Response:
    return _pdf_response(db, "saved-questions")


@router.get("/export/{kind}/{item_id}.pdf")
def export_item(kind: ExportKind, item_id: int, db: Session = Depends(get_db)) -> Response:
    return _pdf_response(db, kind, item_id)


def _pdf_response(db: Session, kind: str, item_id: int | None = None) -> Response:
    try:
        content, filename = pdf_export_service.export(db, kind, item_id)
    except StudyError as exc:
        _raise(exc)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
