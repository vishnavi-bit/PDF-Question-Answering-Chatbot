"""Multiple PDFs: isolation between documents, deletion, duplicates, page limit and large writes."""

from __future__ import annotations

from app.core.config import get_settings
from app.services import vector_store_service
from app.services.vector_store_service import VectorHit
from tests.helpers import make_pdf, upload_pdf

WARRANTY = "Warranty covers motor defects for two years from the date of purchase."
CLEANING = "Cleaning instructions: wash the jar with warm soapy water after each use."


def _upload_two(client):
    first = upload_pdf(client, [WARRANTY], name="warranty.pdf").json()["document"]
    second = upload_pdf(client, [CLEANING], name="cleaning.pdf").json()["document"]
    return first, second


def test_each_pdf_gets_its_own_id_and_metadata(client):
    first, second = _upload_two(client)

    assert first["id"] != second["id"]
    assert first["file_hash"] != second["file_hash"]
    listing = client.get("/api/documents").json()
    assert listing["total"] == 2
    assert {doc["filename"] for doc in listing["documents"]} == {"warranty.pdf", "cleaning.pdf"}


def test_questions_search_only_the_selected_document(client, llm):
    first, second = _upload_two(client)

    response = client.post(
        "/api/chat",
        json={"question": "How long is the warranty?", "document_ids": [first["id"]]},
    )

    sources = response.json()["assistant_message"]["sources"]
    assert sources and all(source["document_id"] == first["id"] for source in sources)
    assert all(source["filename"] == "warranty.pdf" for source in sources)


def test_question_about_an_unselected_document_is_not_answered_from_others(client, llm):
    first, _second = _upload_two(client)

    response = client.post(
        "/api/chat",
        json={"question": "How should I clean the jar?", "document_ids": [first["id"]]},
    )

    body = response.json()
    assert body["answered_from_documents"] is False
    assert body["assistant_message"]["sources"] == []
    assert llm.calls == []  # Gemini is not given text from the unselected PDF


def test_citations_can_come_from_several_selected_documents(client, llm):
    first, second = _upload_two(client)
    llm.reply = (
        '{"answer": "Two facts found.", "source_ids": ["S1", "S2"]}'
    )

    response = client.post(
        "/api/chat",
        json={"question": "warranty and jar cleaning instructions", "document_ids": [first["id"], second["id"]]},
    )

    sources = response.json()["assistant_message"]["sources"]
    filenames = {source["filename"] for source in sources}
    assert filenames == {"warranty.pdf", "cleaning.pdf"}


def test_deleting_one_document_keeps_the_others_searchable(client, llm):
    first, second = _upload_two(client)
    before = vector_store_service.count_vectors()

    assert client.delete(f"/api/documents/{first['id']}").status_code == 204

    assert vector_store_service.count_vectors() < before
    remaining = client.get("/api/documents").json()["documents"]
    assert [doc["id"] for doc in remaining] == [second["id"]]
    response = client.post(
        "/api/chat",
        json={"question": "How do I wash the jar?", "document_ids": [second["id"]]},
    )
    assert response.json()["answered_from_documents"] is True
    assert response.json()["assistant_message"]["sources"][0]["filename"] == "cleaning.pdf"


def test_deleted_document_has_no_vectors_left(client):
    first, second = _upload_two(client)
    client.delete(f"/api/documents/{first['id']}")

    from app.services import embedding_service

    query = embedding_service.embed_query("warranty motor defects")
    assert vector_store_service.search(query, top_k=10, document_ids=[first["id"]]) == []
    assert vector_store_service.search(query, top_k=10, document_ids=[second["id"]]) != []  # the other PDF is untouched


def test_same_pdf_uploaded_again_is_not_indexed_twice(client):
    data = make_pdf([WARRANTY])
    first = upload_pdf(client, name="a.pdf", data=data).json()
    vectors_after_first = vector_store_service.count_vectors()

    second = upload_pdf(client, name="renamed-copy.pdf", data=data).json()

    assert second["duplicate"] is True
    assert second["document"]["id"] == first["document"]["id"]
    assert vector_store_service.count_vectors() == vectors_after_first
    assert client.get("/api/documents").json()["total"] == 1


def test_pdf_over_the_page_limit_is_refused_and_nothing_is_indexed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_pages", 1)
    long_page = "This page has enough readable text to count as a normal text page for indexing. " * 3
    response = upload_pdf(client, [long_page, long_page], name="long.pdf")

    document = response.json()["document"]
    assert document["processing_status"] == "too_large"
    assert "limit is 1 pages" in document["error_message"]
    assert document["total_chunks"] == 0
    assert vector_store_service.count_vectors() == 0


def test_large_document_is_written_to_chroma_in_batches(client):
    # More items than one ChromaDB write accepts (about 5,461), so batching must split them.
    count = 6000
    chunks = [
        _chunk(index)
        for index in range(count)
    ]
    vectors = [[0.01] * 256 for _ in range(count)]

    ids = vector_store_service.add_chunks("big-doc", "big.pdf", chunks, vectors)

    assert len(ids) == count
    assert vector_store_service.count_vectors() == count


def _chunk(index: int):
    from app.services.chunking_service import TextChunk

    return TextChunk(chunk_index=index, page_number=1 + index // 100, content=f"Chunk number {index} of a large test document.")
