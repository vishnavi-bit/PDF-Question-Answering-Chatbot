"""Database tests: tables, relationships, cascading deletes and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.database.connection import SessionLocal, engine
from app.database.models import Conversation, Document, DocumentChunk, Message
from tests.helpers import upload_pdf


def test_expected_tables_exist():
    tables = set(inspect(engine).get_table_names())
    assert {"documents", "document_chunks", "conversations", "messages"} <= tables


def test_each_chunk_row_belongs_to_a_document_and_has_a_vector_id(client):
    upload_pdf(client, ["First sentence about apples. Second sentence about pears."])
    session = SessionLocal()
    try:
        chunks = session.query(DocumentChunk).all()
        assert chunks
        assert all(chunk.document is not None for chunk in chunks)
        assert all(chunk.vector_id.count(":") == 1 for chunk in chunks)
    finally:
        session.close()


def test_duplicate_chunk_index_for_a_document_is_rejected(client):
    upload_pdf(client, ["Some indexed text for the constraint test."])
    session = SessionLocal()
    try:
        document = session.query(Document).one()
        existing = session.query(DocumentChunk).filter_by(document_id=document.id).first()
        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=existing.chunk_index,
                page_number=1,
                content="duplicate",
                vector_id="dup",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_deleting_a_conversation_deletes_its_messages():
    session = SessionLocal()
    try:
        conversation = Conversation(title="Temp")
        session.add(conversation)
        session.flush()
        session.add_all(
            [
                Message(conversation_id=conversation.id, role="user", content="Q"),
                Message(conversation_id=conversation.id, role="assistant", content="A"),
            ]
        )
        session.commit()
        conversation_id = conversation.id

        session.delete(conversation)
        session.commit()

        assert session.query(Message).filter_by(conversation_id=conversation_id).count() == 0
    finally:
        session.close()


def test_deleting_a_document_deletes_its_chunks(client):
    response = upload_pdf(client, ["Text that will be removed together with its chunks."])
    document_id = response.json()["document"]["id"]

    assert client.delete(f"/api/documents/{document_id}").status_code == 204

    session = SessionLocal()
    try:
        assert session.query(DocumentChunk).filter_by(document_id=document_id).count() == 0
        assert session.get(Document, document_id) is None
    finally:
        session.close()


def test_messages_are_kept_in_order(client, llm):
    chat = client.post("/api/chat", json={"question": "First question about the topic?"})
    conversation_id = chat.json()["conversation_id"]
    client.post("/api/chat", json={"question": "Second question?", "conversation_id": conversation_id})

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    roles = [message["role"] for message in detail["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
