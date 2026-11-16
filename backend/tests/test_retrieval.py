"""Vector search tests (ChromaDB + retrieval service)."""

from __future__ import annotations

from app.database.connection import SessionLocal
from app.database.models import Document
from app.services import chunking_service, embedding_service, retrieval_service, vector_store_service
from app.services.pdf_service import ExtractedPage
from tests.helpers import upload_pdf


def _index(document_id: str, filename: str, *texts: str) -> None:
    """Index texts as pages of one document (chunk numbers stay unique within the document)."""
    pages = [ExtractedPage(page_number=number, text=text) for number, text in enumerate(texts, start=1)]
    chunks = chunking_service.chunk_pages(pages, 500, 50)
    vectors = embedding_service.embed_texts([chunk.content for chunk in chunks])
    vector_store_service.add_chunks(document_id, filename, chunks, vectors)
    # hybrid search also needs the document record in SQLite, as a real upload creates it
    session = SessionLocal()
    try:
        if session.get(Document, document_id) is None:
            session.add(Document(id=document_id, filename=filename, original_filename=filename, file_path="",
                                 file_hash=document_id.ljust(64, "0")[:64], file_size=1, page_count=len(texts),
                                 processing_status="ready", total_chunks=len(chunks)))
            session.commit()
    finally:
        session.close()


def test_most_similar_chunk_is_returned_first(client):
    _index(
        "doc-a",
        "a.pdf",
        "Photosynthesis converts sunlight into chemical energy in plants.",
        "Mountains are formed by tectonic plate movements over millions of years.",
    )

    hits = vector_store_service.search(embedding_service.embed_query("How do plants use sunlight?"), top_k=2)

    assert hits[0].text.startswith("Photosynthesis")
    assert hits[0].similarity > hits[-1].similarity


def test_search_can_be_limited_to_selected_documents(client):
    _index("doc-a", "a.pdf", "The budget for marketing was increased this year.")
    _index("doc-b", "b.pdf", "The budget for engineering was reduced this year.")

    query = embedding_service.embed_query("budget this year")
    hits = vector_store_service.search(query, top_k=5, document_ids=["doc-b"])

    assert hits and all(hit.document_id == "doc-b" for hit in hits)


def test_top_k_limits_the_number_of_results(client):
    _index("doc-a", "a.pdf", *[f"Paragraph {index} discusses the same shared topic of testing." for index in range(6)])
    hits = vector_store_service.search(embedding_service.embed_query("shared topic testing"), top_k=3)
    assert len(hits) == 3


def test_same_chunk_added_twice_is_not_duplicated(client):
    _index("doc-a", "a.pdf", "A single unique sentence about rivers and lakes.")
    count_before = vector_store_service.count_vectors()
    _index("doc-a", "a.pdf", "A single unique sentence about rivers and lakes.")
    assert vector_store_service.count_vectors() == count_before


def test_irrelevant_questions_are_filtered_by_similarity_threshold(client):
    _index("doc-a", "a.pdf", "The warranty covers manufacturing defects for two years.")

    hits = retrieval_service.retrieve_chunks("zebra giraffe lions", top_k=5, document_ids=None, min_similarity=0.25)
    assert hits == []


def test_relevant_questions_pass_the_threshold(client):
    _index("doc-a", "a.pdf", "The warranty covers manufacturing defects for two years.")

    hits = retrieval_service.retrieve_chunks(
        "How long does the warranty cover defects?", top_k=5, document_ids=None, min_similarity=0.25
    )
    assert hits and hits[0].filename == "a.pdf"


def test_deleting_a_document_removes_its_vectors(client):
    response = upload_pdf(client, ["Vectors belonging to this document will be deleted soon."])
    document_id = response.json()["document"]["id"]
    assert vector_store_service.count_vectors() > 0

    client.delete(f"/api/documents/{document_id}")

    remaining = vector_store_service.search(
        embedding_service.embed_query("vectors deleted"), top_k=5, document_ids=[document_id]
    )
    assert remaining == []
    session = SessionLocal()
    try:
        assert session.get(Document, document_id) is None
    finally:
        session.close()
