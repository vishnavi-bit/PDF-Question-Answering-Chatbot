# API documentation

The backend is a REST API built with FastAPI. Every endpoint is under `/api`.

**Interactive documentation (Swagger UI):** http://localhost:8000/docs
**Machine-readable schema (OpenAPI):** http://localhost:8000/openapi.json

Errors use the same shape everywhere:

```json
{ "detail": "A short, friendly message" }
```

## Status codes used

| Code | Meaning |
| --- | --- |
| 200 | Success (data returned). |
| 201 | Created (a document was uploaded). |
| 204 | Deleted (no body returned). |
| 400 | The request is understood but not allowed (for example an empty document or a document that is not ready). |
| 404 | Not found (document or conversation does not exist). |
| 413 | File too large. |
| 415 | Not a PDF. |
| 422 | Invalid input (validation error from Pydantic, for example an empty question). |
| 429 | Gemini free-tier rate limit or quota reached. Wait and try again. |
| 502 | Gemini returned an error, or its answer was not usable. |
| 503 | Gemini API key missing or rejected, or Gemini temporarily unavailable after 3 attempts. |
| 504 | Gemini did not finish in time (after up to 3 attempts, within a 150-second total limit). |
| 500 | Unexpected internal error (details are written to the server log only). |

## Health

### `GET /api/health`

```json
{
  "status": "ok",
  "database": "ok",
  "gemini_api_key_configured": false,
  "gemini_model": "gemini-3.6-flash",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
}
```

The key itself is never returned, only whether it is configured.

## Documents

### `POST /api/documents/upload`

Upload one PDF. Form field name: `file`.

```powershell
curl.exe -F "file=@C:\Users\you\Documents\manual.pdf" http://localhost:8000/api/documents/upload
```

Response (201):

```json
{
  "document": {
    "id": "6b35c13fb4e34c42834cac4b093ae4cb",
    "filename": "manual.pdf",
    "original_filename": "manual.pdf",
    "file_size": 2098,
    "file_hash": "4d49…",
    "page_count": 3,
    "processing_status": "ready",
    "error_message": null,
    "total_chunks": 3,
    "created_at": "2026-11-15T10:54:27",
    "updated_at": "2026-11-15T10:54:37"
  },
  "duplicate": false,
  "message": "Indexed 3 text chunks from 3 pages."
}
```

- `duplicate: true` means the exact same file was already indexed, so the existing document is returned.
- If `processing_status` is `needs_ocr`, `password_protected`, `corrupt`, `empty`, `too_large` (more than `MAX_PDF_PAGES` pages) or `failed`, `error_message` explains why.
- Each PDF has its own `id`, `filename`, `file_hash` and `page_count`. Identical files are detected by hash and are not indexed twice.

### `GET /api/documents`

Lists all documents, newest first.

```json
{ "documents": [ { "...": "same fields as above" } ], "total": 1 }
```

### `GET /api/documents/{document_id}`

Returns one document (same fields as above). 404 if unknown.

### `GET /api/documents/{document_id}/file`

Returns the stored PDF (`application/pdf`) so the browser can show it. Only available for documents with status `ready`.

### `DELETE /api/documents/{document_id}`

Deletes the document, its chunks, its vectors and its stored file. Returns 204.

### `POST /api/documents/{document_id}/summary`

Body:

```json
{ "mode": "overview" }
```

`mode` is `overview` or `chapters`.

Response:

```json
{
  "document_id": "6b35…",
  "filename": "manual.pdf",
  "mode": "overview",
  "summary": "The manual explains …",
  "chapters": [],
  "note": null
}
```

For `chapters`, `chapters` contains `{ "title", "page_start", "summary" }` items. If no chapter headings are found, the response uses `mode: "overview"` and a `note` explains why.

## Chat

### `POST /api/chat`

Ask a question. Leave `conversation_id` empty to start a new conversation.

```json
{
  "question": "How long is the warranty?",
  "conversation_id": null,
  "document_ids": [],
  "top_k": 5,
  "answer_style": "detailed"
}
```

| Field | Rules |
| --- | --- |
| `question` | Required, 1 to 2000 characters after trimming. |
| `conversation_id` | Optional. Add it to ask a follow-up in the same conversation. |
| `document_ids` | Optional. Empty means search all ready documents. Each ID must exist and be `ready`. |
| `top_k` | 1 to 20, default 5. How many chunks to retrieve. |
| `answer_style` | `short` or `detailed`. |

Response (200):

```json
{
  "conversation_id": 1,
  "user_message": { "id": 1, "role": "user", "content": "How long is the warranty?", "sources": [], "feedback": null, "created_at": "…" },
  "assistant_message": {
    "id": 2,
    "role": "assistant",
    "content": "The warranty lasts two years from the date of purchase.",
    "sources": [
      {
        "source_id": "S1",
        "document_id": "6b35…",
        "filename": "manual.pdf",
        "page_number": 1,
        "relevant_text": "Product Warranty. The Acme Blender carries a limited warranty of two years…",
        "similarity": 0.61
      }
    ],
    "feedback": null,
    "created_at": "…"
  },
  "answered_from_documents": true,
  "retrieval": {
    "top_k": 5,
    "min_similarity": 0.25,
    "chunks_used": 1,
    "search_variant": "question",
    "best_similarity": 0.61
  }
}
```

- If no chunk is similar enough, `answered_from_documents` is `false`, `sources` is empty, and **Gemini is not called**.
- Errors: 404 (unknown document or conversation), 400 (document not ready), 422 (invalid question), 429/502/503/504 (Gemini problems). A failed question is not saved, so you can send it again.

## Conversations

### `GET /api/conversations`

```json
{
  "conversations": [
    { "id": 1, "title": "How long is the warranty?", "created_at": "…", "updated_at": "…", "message_count": 2 }
  ],
  "total": 1
}
```

### `GET /api/conversations/{conversation_id}`

Returns the conversation and all its messages in order (same message format as above).

### `PATCH /api/conversations/{conversation_id}`

Rename. Body: `{ "title": "New name" }` (1 to 120 characters, not blank).

### `DELETE /api/conversations/{conversation_id}`

Deletes the conversation and its messages. Returns 204.

### `PUT /api/messages/{message_id}/feedback`

Save thumbs up/down on an assistant answer. Body: `{ "feedback": "up" }`, `{ "feedback": "down" }`, or `{ "feedback": null }` to clear it.

## Frontend-to-backend calls

The React app calls these endpoints through `frontend/src/services/api.js`. In development, Vite forwards `/api` to `http://localhost:8000`.

## Study Assistant

All study endpoints use the selected PDFs (`document_ids`; an empty list means all ready PDFs). Generated items always cite real excerpts: each item has `sources` with `filename`, `page_number` and `document_id`. Items that cannot be grounded are dropped.

| Method and path | Purpose |
| --- | --- |
| `POST /api/study/notes` | `{"mode": "overview" or "chapters", "document_ids": []}` - study notes, key points, definitions, simple explanations, or chapter summaries |
| `POST /api/study/quizzes` | `{"count": 1 to 30, "difficulty": "easy", "medium" or "hard", "document_ids": []}` - creates a quiz (answers are not returned) |
| `GET /api/study/quizzes/{id}` | Reopen a quiz without answers |
| `POST /api/study/quizzes/{id}/attempts` | `{"answers": [0, null, 2, ...]}` - grades on the server, saves the attempt, returns score, correct answers, explanations and sources |
| `POST /api/study/flashcards` | `{"count": 5 or 10 or 20, "document_ids": []}` - flashcard deck with sources |
| `GET /api/study/flashcards/{id}` | Deck with `studied_indices` |
| `PUT /api/study/flashcards/{id}/progress` | `{"card_index": 0, "studied": true}` - saves studied cards |
| `POST /api/study/exams` | `{"short_count": 5, "long_count": 2, "document_ids": []}` - short and long answer questions |
| `GET /api/study/exams/{id}` | Reopen an exam paper |
| `POST /api/study/explain` | `{"topic": "photosynthesis", "follow_up": "optional question", "document_ids": []}` - simple explanation with an example and step-by-step points, or `found: false` when the PDFs do not mention it (no Gemini call) |
| `GET /api/study/progress` | Quiz attempts, overall accuracy, accuracy by topic, weak topics (below 60%), flashcard progress |

Errors: 400 (no ready PDFs), 404 (unknown PDF or study item), 422 (invalid count or answers), 429/502/503/504 (Gemini problems, same meaning as chat).

The `GET /api/study/exams/{id}` response now includes `topic` and `importance` (`high`, `medium` or `low`) for each question.

## Study tools (Phase 4)

Saved notes, timed mock exams, review scheduling, saved questions and the learning path. The learning path only uses recorded data.

| Method and path | Purpose |
| --- | --- |
| `POST /api/study/notes/saved` | `{"mode": "overview", "chapter" or "topic", "length": "short" or "detailed", "topic": "...", "document_ids": []}` - create and save notes. A topic not found in the PDFs returns 400 and does not call Gemini. |
| `GET /api/study/notes` | List saved notes (`{"notes": [...], "total": n}`) |
| `GET /api/study/notes/{id}` | Read one note with its body and sources |
| `PUT /api/study/notes/{id}` | `{"title": "...", "body": {...}}` - rename or edit. Every kept item must keep at least one source (422 otherwise). |
| `DELETE /api/study/notes/{id}` | Delete (204) |
| `POST /api/study/mock-exams` | `{"difficulty", "mcq_count": 1 to 30, "descriptive_count": 0 to 10, "duration_minutes": 5 to 180, "document_ids": []}` - generate a paper. The response contains no answers. |
| `GET /api/study/mock-exams/{id}` | The paper without answers |
| `DELETE /api/study/mock-exams/{id}` | Delete a paper and its attempts (204) |
| `POST /api/study/mock-exams/{id}/start` | Start a timed attempt. Returns `attempt_id`, `deadline` and `duration_seconds`. The server sets the deadline. |
| `POST /api/study/mock-exam-attempts/{id}/submit` | `{"answers": [0, null, ...], "descriptive": ["..."], "auto_submitted": false}` - grades the multiple-choice answers on the server. A submission after the deadline plus a 30-second grace period is marked `late`. A second submission returns 409. A wrong number of answers returns 422. |
| `GET /api/study/mock-exam-attempts/{id}` | Result with correct answers, explanations and model answers. Returns 409 before submission. |
| `GET /api/study/mock-exam-attempts` | Attempt history |
| `POST /api/study/saved-questions` | `{"kind": "short", "long" or "mcq", "question", "answer", "sources": []}` |
| `GET /api/study/saved-questions` / `DELETE /api/study/saved-questions/{id}` | List and remove saved questions |
| `PUT /api/study/flashcards/{deck_id}/review` | `{"card_index": 0, "status": "known" or "need_practice"}` - applies the SM-2 schedule and returns `due_date`, `interval_days`, `ease_factor` and `repetitions`. A card that does not exist returns 422. |
| `GET /api/study/revision/today` | Revision tasks due today, flashcards due, and counts |
| `GET /api/study/revision/upcoming?days=7` | Tasks and cards due in the next N days (1 to 60) |
| `POST /api/study/revision-plans` | `{"deck_id": 1}` - creates tasks for days 1, 3, 7 and 14 |
| `POST /api/study/revision-plans/{id}/complete` | `{"completed": true}` |
| `GET /api/study/learning-path` | Steps built from quiz results, due cards and open tasks. With no quiz results it says so and lists no weak topics. |

## PDF extraction and OCR detection (Phase 7)

- `GET /api/documents` and `GET /api/documents/{id}` include `table_count` (ruled tables indexed) and `pages_without_text` (blank or image-only pages).
- `GET /api/health` includes `ocr`: `tesseract_installed` (true or false), and `ocr_enabled`, which is always `false` in this version. OCR is detected only, never installed or run.
- A PDF with almost no text gets status `needs_ocr`, and the message says whether Tesseract is installed.
- A PDF over `MAX_PDF_PAGES` (default 1000) gets status `too_large` before any text is indexed.
- Uploading the same file again returns the document that is already indexed.

## Mind maps and PDF exports (Phase 5)

| Method and path | Purpose |
| --- | --- |
| `POST /api/study/mind-maps` | `{"document_ids": []}` - builds a tree with Gemini. Nodes without a real source are dropped. If no node is grounded, nothing is saved (502). The centre is the PDF name. |
| `GET /api/study/mind-maps` | List maps (`{"mind_maps": [...], "total": n}`) |
| `GET /api/study/mind-maps/{id}` | Read one map (`tree` with `centre`, `branches` and `children`, each with `sources`) |
| `PUT /api/study/mind-maps/{id}` | `{"title": "..."}` - rename |
| `DELETE /api/study/mind-maps/{id}` | Delete (204) |
| `GET /api/study/export/{kind}/{id}.pdf` | Download a PDF. `kind` is one of `notes`, `quiz`, `quiz-attempt`, `flashcards`, `exam`, `mock-exam`, `mock-exam-attempt` or `mind-map`. The response has `Content-Disposition: attachment`. A mock exam result that is not submitted returns 409. |
| `GET /api/study/export/saved-questions.pdf` | Download all saved questions |

Every PDF has a title, a subtitle, page numbers in the footer, and a "Source: file, page N" line under each item. Characters that the standard PDF font cannot show are replaced with `?`.

## Chat streaming

`POST /api/chat/stream` takes the same body as `POST /api/chat`, plus an optional `client_request_id` (up to 64 characters). It returns `text/event-stream`:

| Event | Data |
| --- | --- |
| `meta` | `{"retrieval": {...}}` (sent before any text) |
| `delta` | `{"text": "..."}` (answer text as it is written; the citation line is hidden) |
| `done` | Same fields as the `POST /api/chat` response (`conversation_id`, `user_message`, `assistant_message`, `answered_from_documents`, `retrieval`) |
| `error` | `{"status": 502, "detail": "..."}` (a problem after the answer started; nothing is saved) |

Problems before the first `delta` are normal HTTP errors: 503 (key missing, cooldown, rejected key), 504 (Gemini did not answer in time), 429 (rate limit), 409 (the same `client_request_id` is still being processed).

Repeated requests with the same `client_request_id` return the first result instead of saving a second copy.

`GET /api/health` also returns `gemini_status` with `open`, `seconds_left` and `consecutive_failures` for the cooldown. It contains no secrets.

## Chat regenerate and search (Phase 2)

- `POST /api/chat/regenerate` (Server-Sent Events, same events as `/api/chat/stream`): body `{"conversation_id": 1, "document_ids": [], "top_k": 5, "answer_style": "detailed"}`. Answers the last question again. The previous answer is replaced only after the new one succeeds; if it fails, the old answer is kept. Returns 400 when the chat has no question, and 404 for an unknown chat.
- `GET /api/conversations?q=text`: lists chats whose title or message text contains `text` (case-insensitive). Without `q` the full list is returned.

