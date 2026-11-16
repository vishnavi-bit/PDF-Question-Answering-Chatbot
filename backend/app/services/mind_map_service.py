"""
Phase 5 mind maps: a topic tree built from the selected PDFs and saved in SQLite.

Grounding rules (same as the study tools):
- Gemini only sees excerpts from the selected PDFs.
- A branch or subtopic is kept only if it cites at least one real excerpt id.
  Citations (filename and page) are built from our own excerpt data, never from model text.
- The centre of the map is the PDF name(s), not model text, so nothing is invented there.
- If no branch is grounded, nothing is saved and the student is told why.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MindMap
from app.services import study_context, study_service
from app.services.study_context import StudyError, excerpt_map

MAX_BRANCHES = 8
MAX_CHILDREN = 6
MAX_LABEL_CHARS = 120
MAX_TITLE_CHARS = 200

MAP_INSTRUCTION = (
    "Make a mind map of the main topics in <study_excerpts>. "
    "Give up to 8 branches (main topics). Each branch has a short 'label' (at most 6 words), 'source_ids', "
    "and up to 6 'children' (subtopics), each with its own 'label' and 'source_ids'. "
    "Only include topics the excerpts actually cover. "
    'Output: {"branches": [{"label": "...", "source_ids": ["S1"], '
    '"children": [{"label": "...", "source_ids": ["S1"]}]}]}'
)


def _label(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split())[:MAX_LABEL_CHARS]
    return text or None


def _source_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _grounded_node(raw: Any, by_id: dict, ids: itertools.count) -> dict[str, Any] | None:
    """One node, or None when it has no label or no real source."""
    if not isinstance(raw, dict):
        return None
    label = _label(raw.get("label"))
    if label is None:
        return None
    sources = [c.model_dump() for c in study_service._citations(_source_ids(raw.get("source_ids")), by_id)]
    if not sources:
        return None
    return {"id": f"n{next(ids)}", "label": label, "sources": sources, "children": []}


def build_tree(data: dict[str, Any], excerpts: list[study_context.StudyExcerpt], centre: str) -> dict[str, Any]:
    """Turn Gemini's JSON into a tree. Ungrounded nodes are dropped, with their subtopics."""
    by_id = excerpt_map(excerpts)
    ids = itertools.count(1)
    raw_branches = data.get("branches")
    branches: list[dict[str, Any]] = []
    if isinstance(raw_branches, list):
        for raw in raw_branches[:MAX_BRANCHES]:
            branch = _grounded_node(raw, by_id, ids)
            if branch is None:
                continue
            raw_children = raw.get("children") if isinstance(raw, dict) else None
            if isinstance(raw_children, list):
                for raw_child in raw_children[:MAX_CHILDREN]:
                    child = _grounded_node(raw_child, by_id, ids)
                    if child is not None:
                        branch["children"].append(child)
            branches.append(branch)
    return {"centre": centre, "branches": branches}


def count_nodes(tree: dict[str, Any]) -> int:
    return sum(1 + len(branch.get("children", [])) for branch in tree.get("branches", []))


def generate_mind_map(db: Session, document_ids: list[str]) -> MindMap:
    excerpts = study_context.select_study_excerpts(db, document_ids)
    data = study_service._ask(MAP_INSTRUCTION, excerpts, study_service._tokens_for(len(excerpts)))
    names = study_service._document_names(excerpts)
    centre = (", ".join(names) or "Selected PDFs")[:MAX_LABEL_CHARS]
    tree = build_tree(data, excerpts, centre)
    if not tree["branches"]:
        raise StudyError(502, "no_grounded_map",
                         "No mind map could be made from the text of the selected PDFs. Try other PDFs or a larger part of the document.")
    mind_map = MindMap(
        title=study_service._title("Mind map", excerpts)[:MAX_TITLE_CHARS],
        document_ids_json=json.dumps(sorted({excerpt.document_id for excerpt in excerpts})),
        tree_json=json.dumps(tree),
    )
    db.add(mind_map)
    db.commit()
    db.refresh(mind_map)
    return mind_map


def _load(db: Session, map_id: int) -> MindMap:
    mind_map = db.get(MindMap, map_id)
    if mind_map is None:
        raise StudyError(404, "mind_map_not_found", "This mind map was not found.")
    return mind_map


def mind_map_out(mind_map: MindMap) -> dict[str, Any]:
    tree = json.loads(mind_map.tree_json)
    return {
        "id": mind_map.id,
        "title": mind_map.title,
        "document_ids": json.loads(mind_map.document_ids_json),
        "tree": tree,
        "node_count": count_nodes(tree),
        "created_at": mind_map.created_at.isoformat() if mind_map.created_at else None,
    }


def list_mind_maps(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(select(MindMap).order_by(MindMap.id.desc())).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "node_count": count_nodes(json.loads(row.tree_json)),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def get_mind_map(db: Session, map_id: int) -> dict[str, Any]:
    return mind_map_out(_load(db, map_id))


def rename_mind_map(db: Session, map_id: int, title: str) -> dict[str, Any]:
    clean = " ".join(title.split())[:MAX_TITLE_CHARS]
    if len(clean) < 2:
        raise StudyError(422, "title", "Give the mind map a title of at least 2 characters.")
    mind_map = _load(db, map_id)
    mind_map.title = clean
    db.commit()
    db.refresh(mind_map)
    return mind_map_out(mind_map)


def delete_mind_map(db: Session, map_id: int) -> None:
    db.delete(_load(db, map_id))
    db.commit()
