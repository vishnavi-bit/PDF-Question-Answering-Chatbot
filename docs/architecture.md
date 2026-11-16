# Architecture

This document explains how the AI PDF Question Answering Chatbot is built. It is written for beginners, so each technical idea is explained once in plain English.

## The big picture

```
 Browser (React app)                 Backend (FastAPI, Python)                 Storage (on your computer)
 ───────────────────                 ─────────────────────────                 ──────────────────────────
 Upload PDF  ───────────────────────▶ upload.py → rag_service (ingestion)  ──▶  storage/uploads/   (the PDF file)
                                                    │                      ──▶  storage/chroma_db/ (vectors)
                                                    └─────────────────────────▶ backend/data/app.db (SQLite)
 Ask question ──────────────────────▶ chat.py → rag_service (answering)
                                                    │
                                                    └──▶ Gemini API (internet)
 Show answer + citations ◀────────── JSON response
```

- The **frontend** (React) only shows things and sends requests. It never talks to Gemini and never sees the API key.
- The **backend** (FastAPI) does all the work: reading PDFs, searching, and calling Gemini.
- **SQLite** stores normal application data: documents, conversations, and messages.
- **ChromaDB** stores the "vectors" (numbers that represent meaning) used for search.

## What is RAG?

**RAG** means *Retrieval-Augmented Generation*. In plain English:

1. **Retrieval**: find the parts of your PDFs that are most related to the question.
2. **Augmented**: give those parts to the AI together with the question.
3. **Generation**: the AI writes an answer using only those parts.

This is much more reliable than asking the AI directly, because the answer is based on your document, and the app can show the page it came from.

## Key concepts in simple English

| Term | Meaning |
| --- | --- |
| **Chunk** | A small piece of text (about 1000 characters) cut from a PDF page. Small pieces are easier to search than whole books. |
| **Overlap** | Neighbouring chunks share about 150 characters, so a sentence cut in half is still complete in one of them. |
| **Embedding** | A list of 384 numbers that describes the *meaning* of a piece of text. Texts with similar meaning get similar numbers. |
| **Vector** | Another word for an embedding stored in the database. |
| **Semantic search** | Searching by meaning rather than exact words. "How long is the guarantee?" finds text that says "warranty lasts two years". |
| **Similarity** | A score between 0 and 1 saying how close two embeddings are (we use cosine similarity). |
| **Threshold** | The minimum similarity needed before a chunk is used. Below it, the chunk is ignored. |
| **Top-k** | How many best-matching chunks we keep (default 5). |

## The two pipelines

### 1. Document ingestion (when you upload a PDF)

```
PDF upload
  → validate (is it really a PDF? is it under 20 MB? already uploaded?)
  → text extraction (PyMuPDF, keeps page numbers)
  → text cleaning (fix hyphenation, extra spaces, blank lines)
  → chunking (LangChain RecursiveCharacterTextSplitter, per page)
  → embeddings (sentence-transformers all-MiniLM-L6-v2)
  → ChromaDB storage (vectors + chunk text + metadata)
  → SQLite metadata storage (document row + chunk rows)
```

If the PDF has no selectable text (a scan), the process stops with status `needs_ocr`, and the file is deleted because it cannot be searched.

### 2. Question answering (when you ask a question)

```
User question
  → validation (not empty, at most 2000 characters)
  → question embedding (same model as the chunks!)
  → semantic search in ChromaDB (optionally only in the selected documents)
  → similarity threshold (weak matches are dropped)
  → if nothing is left: answer "not found" WITHOUT calling Gemini
  → context preparation (each chunk wrapped as excerpt S1, S2, …, with file name and page)
  → Gemini API (system rules + excerpts + recent conversation + question)
  → answer parsing and validation (JSON structure checked with Pydantic)
  → citation formatting (only the excerpts the model says it used)
  → saved to SQLite, returned to the frontend
```

**Why the threshold matters:** if you ask "What is the recipe for chocolate cake?" about a blender manual, no chunk is similar enough, so the app says the answer is not in the documents. Without this check, the AI would be given unrelated text and could invent an answer.

**Why the same embedding model is used for everything:** two embeddings can only be compared if they came from the same model. Changing `EMBEDDING_MODEL` means existing documents must be uploaded again.

## Security design (summary)

- The Gemini API key lives only in `backend/.env` and is read by the backend. It is never sent to the browser and never logged.
- Stored files get random names (`<document id>.pdf`). The name you uploaded is only displayed.
- File names are cleaned (no folders, no unusual characters). Paths are checked so files outside the storage folder cannot be read or deleted.
- Deleted files are overwritten with zeros before they are removed.
- Gemini is told that PDF text is untrusted. Text in excerpts is wrapped in tags, and any attempt to close the tag early is neutralised.
- Internal errors return a generic message. Details go to the server log.

See the README section "Security limitations" for what is **not** protected yet.

## Frontend structure

- `App.jsx` sets up the page layout (sidebar, top bar) and the routes.
- `context/ChatContext.jsx` holds shared state: documents, selected documents, upload progress, and the conversation list.
- `hooks/useChat.js` manages one conversation: loading messages, sending questions, and feedback.
- `services/api.js` is the only place that calls the backend.
- `components/` contains small reusable pieces (chat bubbles, citations, the PDF viewer, the uploader).
- `pages/` contains the three screens: Home, Chat and History.

The PDF viewer uses the browser's built-in PDF viewer, which accepts `#page=` and `#zoom=` in the address. This is why page navigation and zoom work without a heavy PDF library.

## Backend structure

| Folder | Purpose |
| --- | --- |
| `app/main.py` | Creates the FastAPI app, CORS, routes, error handling, and serves the built frontend in Docker. |
| `app/api/` | HTTP endpoints (thin: they check input and call services). |
| `app/services/` | The real work: PDF, chunking, embeddings, vector store, retrieval, Gemini (llm), RAG, chat, summaries. |
| `app/database/` | SQLAlchemy engine, models and initialisation. |
| `app/schemas/` | Pydantic models that define request and response shapes. |
| `app/core/` | Settings (from environment variables) and security helpers. |
| `tests/` | Automated tests (no real API key or internet needed for most of them). |

More detail: [database_design.md](database_design.md), [api_documentation.md](api_documentation.md), [setup_guide.md](setup_guide.md).

## Study Assistant

- `services/study_context.py` picks the text sent to Gemini: an equal share of about 12,000 characters per selected PDF, sampled evenly across its pages. For a topic it uses the existing semantic search.
- `services/study_service.py` builds the prompts, calls the existing `llm_service.complete` (with retries, time limits and missing-key handling), and applies grounding: an item is kept only if it cites an excerpt that exists. Citations come from our excerpt data, never from the model's text.
- `services/study_progress_service.py` grades quizzes on the server, saves attempts, and calculates topic accuracy and weak topics.
- The frontend Study page (`pages/Study.jsx`) reuses the sidebar PDF selection. Each tab is a component in `components/study/`.

## Gemini reliability layer (Phase 1)

- `services/llm_service.py` contains the retry loop (max 3 attempts), the total time budget (150 s), the cooldown (circuit breaker), the answer cache, the in-flight de-duplication, and streaming (`stream_text`).
- `services/request_guard.py` remembers recent results for repeated chat questions (`client_request_id`) and study generation requests, and stops identical requests from running twice at the same time.
- `services/rag_service.py` builds the prompt in one shared place (`_prepare`), used by both the complete answer and the streamed answer. Streamed answers use a `SOURCES:` line that is hidden from the text and checked against the excerpts we sent.
- `database/migrations.py` and `alembic/` manage the schema. Migrations take a backup before they change anything.

## PDF extraction (Phase 7)

- `services/pdf_service.py` reads text page by page (a damaged page is skipped) and finds ruled tables with pdfplumber. Table text is chunked like any other text, so it is searchable and keeps its page number.
- `services/ocr_service.py` only checks whether `tesseract` is on the PATH and writes the messages. It never runs OCR.
- `services/rag_service.py` embeds chunks in batches and records `table_count` and `pages_without_text` on the document.

## Study tools and exports (Phases 4 and 5)

- `services/revision_service.py` implements the SM-2 spaced-repetition rule (`sm2_next`), records reviews, and creates revision plans. Review dates use the server's date.
- `services/study_tools_service.py` handles saved notes (with source checks on edits), timed mock exams (the server sets the deadline and grades answers), saved questions and the learning path.
- `services/mind_map_service.py` builds a mind map from Gemini's JSON. It reuses the grounding helpers from `study_service.py`, so a node is kept only if it cites a real excerpt.
- `services/pdf_export_service.py` builds PDFs with ReportLab from the same stored data the screens show. Text is converted to Windows-1252 so the standard fonts can draw it.
- `api/study_tools.py` and `api/study_export.py` hold the routes under `/api/study`. Both are registered in `main.py`.
- The frontend Study page has nine tabs. Each is a component in `components/study/`: `MockExamPanel`, `RevisionPanel`, `MindMapPanel`, and `SavedNotes` (inside the Notes tab). `ExportButton` downloads a PDF through the API client.
- Timed mock exams: the browser shows the time left from the server's `deadline`. When time runs out, it sends the answers with `auto_submitted: true`. The server also marks any submission that arrives after the grace period as `late`.
