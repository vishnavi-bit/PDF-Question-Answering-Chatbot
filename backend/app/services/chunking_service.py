"""
Text chunking with LangChain's RecursiveCharacterTextSplitter.

Each page is split on its own, so every chunk knows exactly which page it
came from. The splitter prefers paragraph breaks, then line breaks, then
spaces, so chunks break at natural places where possible.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.pdf_service import ExtractedPage


@dataclass
class TextChunk:
    chunk_index: int   # position in the whole document (0, 1, 2, ...)
    page_number: int   # page the chunk came from (1-based)
    content: str


def chunk_pages(pages: list[ExtractedPage], chunk_size: int, chunk_overlap: int) -> list[TextChunk]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
        strip_whitespace=True,
    )

    chunks: list[TextChunk] = []
    for page in pages:
        if not page.text.strip():
            continue  # skip blank pages
        for piece in splitter.split_text(page.text):
            piece = piece.strip()
            if piece:
                chunks.append(TextChunk(chunk_index=len(chunks), page_number=page.page_number, content=piece))
    return chunks
