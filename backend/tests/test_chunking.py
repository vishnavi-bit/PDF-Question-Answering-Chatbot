"""Chunking tests (LangChain RecursiveCharacterTextSplitter)."""

from __future__ import annotations

import pytest

from app.services.chunking_service import chunk_pages
from app.services.pdf_service import ExtractedPage


def _long_text(sentences: int) -> str:
    return " ".join(f"Sentence number {i} explains part {i} of the topic." for i in range(sentences))


def test_chunks_keep_their_page_numbers():
    pages = [
        ExtractedPage(page_number=1, text=_long_text(5)),
        ExtractedPage(page_number=2, text="Short page on page two."),
    ]
    chunks = chunk_pages(pages, chunk_size=200, chunk_overlap=20)

    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert all(chunk.page_number == 1 for chunk in chunks if "number" in chunk.content)


def test_chunks_respect_the_size_limit_and_are_numbered_in_order():
    pages = [ExtractedPage(page_number=1, text=_long_text(60))]
    chunks = chunk_pages(pages, chunk_size=300, chunk_overlap=30)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 300 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_neighbouring_chunks_overlap():
    pages = [ExtractedPage(page_number=1, text=_long_text(60))]
    chunks = chunk_pages(pages, chunk_size=300, chunk_overlap=80)

    # The end of one chunk should reappear at the start of the next one.
    shared = [
        (first, second)
        for first, second in zip(chunks, chunks[1:])
        if any(word in second.content for word in first.content.split()[-5:])
    ]
    assert shared, "expected some shared text between neighbouring chunks"


def test_blank_pages_produce_no_chunks():
    chunks = chunk_pages([ExtractedPage(page_number=1, text="   \n  ")], chunk_size=100, chunk_overlap=10)
    assert chunks == []


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_pages([ExtractedPage(page_number=1, text="text")], chunk_size=100, chunk_overlap=100)
