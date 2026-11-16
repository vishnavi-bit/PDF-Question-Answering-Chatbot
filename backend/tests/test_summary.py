"""Summary tests: overview, chapter detection and error handling."""

from __future__ import annotations

from app.database.connection import SessionLocal
from app.database.models import DocumentChunk
from app.services.summary_service import detect_heading, split_into_sections
from tests.helpers import upload_pdf

CHAPTER_TEXT = (
    "Chapter 1 Introduction\n"
    "This chapter introduces the topic of solar energy and its history.\n"
    "Chapter 2 Methods\n"
    "The methods section explains how panels were measured in the field."
)


def test_detect_heading_recognises_chapters_and_numbered_titles():
    assert detect_heading("Chapter 3 Results") == "Chapter 3 Results"
    assert detect_heading("2.1 Data Collection") == "2.1 Data Collection"
    assert detect_heading("This is a normal sentence that continues for a while.") is None
    assert detect_heading("3 Mbps") is None


def test_split_into_sections_groups_text_under_headings():
    chunks = [
        DocumentChunk(document_id="d", chunk_index=0, page_number=1, content=CHAPTER_TEXT, vector_id="x"),
    ]
    sections = split_into_sections(chunks)
    assert [section.title for section in sections] == ["Chapter 1 Introduction", "Chapter 2 Methods"]
    assert "solar energy" in " ".join(sections[0].texts)


def test_overview_summary_uses_gemini(client, llm):
    document = upload_pdf(client, ["A long report about renewable energy and its benefits."]).json()["document"]
    llm.reply = "The report discusses renewable energy benefits."

    response = client.post(f"/api/documents/{document['id']}/summary", json={"mode": "overview"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "The report discusses renewable energy benefits."
    assert body["mode"] == "overview"
    assert len(llm.calls) == 1


def test_chapter_summaries_summarise_each_section(client, llm):
    document = upload_pdf(client, [CHAPTER_TEXT]).json()["document"]
    llm.reply = "- point one\n- point two"

    body = client.post(f"/api/documents/{document['id']}/summary", json={"mode": "chapters"}).json()

    assert body["mode"] == "chapters"
    assert [chapter["title"] for chapter in body["chapters"]] == ["Chapter 1 Introduction", "Chapter 2 Methods"]
    assert len(llm.calls) == 2


def test_chapter_mode_without_headings_falls_back_to_overview(client, llm):
    document = upload_pdf(client, ["Plain text with no headings at all, just a simple sentence."]).json()["document"]

    body = client.post(f"/api/documents/{document['id']}/summary", json={"mode": "chapters"}).json()

    assert body["mode"] == "overview"
    assert "No chapter headings" in body["note"]


def test_summary_of_unknown_document_returns_404(client):
    assert client.post("/api/documents/nope/summary", json={"mode": "overview"}).status_code == 404


def test_summary_of_scanned_document_is_refused(client, llm):
    from tests.helpers import make_scanned_pdf

    document = upload_pdf(client, name="scan.pdf", data=make_scanned_pdf()).json()["document"]
    response = client.post(f"/api/documents/{document['id']}/summary", json={"mode": "overview"})
    assert response.status_code == 400
    assert llm.calls == []


def test_summary_uses_the_stored_chunks(client, llm):
    document = upload_pdf(client, ["Stored text used for the summary input."]).json()["document"]
    session = SessionLocal()
    try:
        assert session.query(DocumentChunk).filter_by(document_id=document["id"]).count() >= 1
    finally:
        session.close()
    client.post(f"/api/documents/{document['id']}/summary", json={"mode": "overview"})
    assert "Stored text used for the summary input." in llm.calls[-1]["messages"][0]["content"]
