# Database design

The app uses two storage systems, each for a different job:

| Storage | Holds | Why |
| --- | --- | --- |
| **SQLite** (`backend/data/app.db` by default) | Documents, chunk text, conversations, messages | Normal relational data, easy to query, one file. |
| **ChromaDB** (`storage/chroma_db/`) | Embedding vectors, plus the chunk text and metadata used for search | Built for fast "find similar vectors" searches. |

Vectors are large, and they are only needed for search. So they live in ChromaDB, and SQLite only keeps a `vector_id` that links each chunk row to its vector. This avoids storing large vector data twice.

SQLAlchemy creates the tables automatically on startup (`app/database/init_db.py`). The models are in `app/database/models.py`.

## Tables

### `documents`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT (32), **primary key** | Random hexadecimal ID, for example `6b35c13f…`. |
| `filename` | TEXT (255) | Cleaned name shown in the app. |
| `original_filename` | TEXT (255) | The name the file had when uploaded. |
| `file_path` | TEXT (512) | Location of the stored PDF. Empty for documents that failed. |
| `file_hash` | TEXT (64), indexed | SHA-256 of the file. Used to detect duplicate uploads. |
| `file_size` | INTEGER | Size in bytes. |
| `page_count` | INTEGER | Number of PDF pages. |
| `processing_status` | TEXT (32), indexed | `processing`, `ready`, `needs_ocr`, `password_protected`, `corrupt`, `empty` or `failed`. |
| `error_message` | TEXT, nullable | Friendly explanation when processing did not succeed. *(Not in the original brief; added so the app can explain problems.)* |
| `total_chunks` | INTEGER | Number of chunks indexed. |
| `created_at` / `updated_at` | DATETIME | Set by the database. |

### `document_chunks`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER, **primary key** | Auto-numbered. |
| `document_id` | TEXT, **foreign key** → `documents.id`, indexed | `ON DELETE CASCADE`: deleting a document deletes its chunks. |
| `chunk_index` | INTEGER | Position of the chunk in the whole document (0, 1, 2, …). |
| `page_number` | INTEGER | Page the chunk came from (starts at 1). |
| `content` | TEXT | The chunk text. Used for summaries and for re-checking citations. |
| `vector_id` | TEXT (128) | ID of the matching vector in ChromaDB, written as `<document_id>:<chunk_index>`. |
| `created_at` | DATETIME | Set by the database. |

Constraints and indexes:
- `UNIQUE (document_id, chunk_index)`: a chunk number can only appear once per document, so no duplicates.
- Index on `(document_id, page_number)` for page lookups.

### `conversations`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER, **primary key** | |
| `title` | TEXT (120) | Starts as the first 60 characters of the first question. Can be renamed. |
| `created_at` / `updated_at` | DATETIME | `updated_at` is indexed so the newest chats are listed first. |

### `messages`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER, **primary key** | Also used as the target of feedback. |
| `conversation_id` | INTEGER, **foreign key** → `conversations.id`, indexed | `ON DELETE CASCADE`. |
| `role` | TEXT (16) | `user` or `assistant`. |
| `content` | TEXT | The question or the answer text. |
| `sources_json` | TEXT, nullable | For assistant messages: the citations (document, file name, page, relevant text, similarity) as JSON. *(Added to the brief so the history can show citations again.)* |
| `feedback` | TEXT (8), nullable | `up`, `down` or empty. *(Added so the thumbs buttons are saved.)* |
| `created_at` | DATETIME | |

Index on `(conversation_id, id)` keeps messages in order.

## Relationships

```
documents 1 ──────── * document_chunks        (delete a document → its chunks are deleted)
   │
   └── (vectors in ChromaDB, matched by vector_id, removed when the document is deleted)

conversations 1 ──── * messages               (delete a conversation → its messages are deleted)
```

Foreign keys are enforced: the app turns on `PRAGMA foreign_keys=ON` for every SQLite connection, because SQLite does not check them by default.

## What happens when a document is deleted

1. Its vectors are removed from ChromaDB (`where document_id = …`).
2. Its PDF file is overwritten with zeros and removed from `storage/uploads/`.
3. The `documents` row is deleted, and the database cascades to `document_chunks`.

Messages that cite the document keep their text and citation details, so old answers stay readable. Opening the source of a deleted document will show that the file is no longer available.

## Why the chunk text is stored twice

The chunk text is stored in SQLite (for summaries and history) and in ChromaDB (returned by search). The text is small compared with the vectors, and keeping it in SQLite lets the summary feature work without touching the vector store.

## Schema diagram

```
┌──────────────────────┐        ┌────────────────────────┐
│ documents            │ 1    * │ document_chunks        │
│ id (PK)              │───────▶│ id (PK)                │
│ filename             │        │ document_id (FK)       │
│ file_hash            │        │ chunk_index            │
│ processing_status    │        │ page_number            │
│ page_count           │        │ content                │
│ total_chunks         │        │ vector_id ──▶ ChromaDB │
└──────────────────────┘        └────────────────────────┘

┌──────────────────────┐ 1    * ┌────────────────────────┐
│ conversations        │───────▶│ messages               │
│ id (PK)              │        │ id (PK)                │
│ title                │        │ conversation_id (FK)   │
│ updated_at           │        │ role                   │
└──────────────────────┘        │ content                │
                                │ sources_json           │
                                │ feedback               │
                                └────────────────────────┘
```

## Migrations

The schema is managed with Alembic (`backend/alembic/versions/`). Revisions:

| Revision | What it does |
| --- | --- |
| `0001_baseline` | Creates the original seven tables if they are missing (`documents`, `document_chunks`, `conversations`, `messages`, `study_sets`, `quiz_attempts`, `flashcard_studies`). Existing data is kept. |
| `0002_study_upgrade` | Adds `study_notes`, `mock_exams`, `mock_exam_attempts`, `flashcard_reviews`, `revision_plans`, `mind_maps`, `research_reports` and `saved_questions`. It only creates tables, so no existing table or row is changed. |

| `0003_document_extraction` | Adds `documents.table_count` and `documents.pages_without_text` (both default 0). Adds only columns that are missing, so it works on fresh and existing databases. |

Before a migration runs, the app copies `app.db` into `backend/data/backups/` (`auto-before-migration-*.db`, made with SQLite's online backup API). Migrations run automatically when the backend starts. Downgrades are no-ops, so a downgrade never removes data.

Manual backups were also taken before each phase (for example `backend/data/backups/pre-phase4-…`). Each one contains `app.db`, `storage/uploads` and `storage/chroma_db`.

Never delete `app.db` to fix a schema problem, because that would leave orphaned vectors in ChromaDB. If something goes wrong, stop the backend and copy a backup from `backend/data/backups/` back into place.

## Study Assistant tables

These tables were added for the Study Assistant. Existing tables were not changed.

### `study_sets`
Saved quizzes, flashcard decks and exam papers.

| Column | Notes |
| --- | --- |
| `id` | Primary key |
| `kind` | `quiz`, `flashcards` or `exam` (indexed). Saved questions and mock exams have their own tables. |
| `title` | Shown in lists, for example `Quiz (5 questions) from manual.pdf` |
| `document_ids_json` | The PDFs the set was made from |
| `payload_json` | Generated items with correct answers and sources. The API never returns correct answers before grading. |
| `created_at` | |

### `quiz_attempts`
One graded attempt. `study_set_id` references `study_sets.id` with `ON DELETE CASCADE`. Columns: `total`, `correct`, `percent`, `answers_json` (topic, chosen option, correct option and result for each question), `created_at`.

### `flashcard_studies`
Which cards were marked studied. `study_set_id` references `study_sets.id` with `ON DELETE CASCADE`. Unique `(study_set_id, card_index)`, so a card is stored at most once.

Deleting a PDF does not delete saved attempts. Attempts stay in the progress history.

### `study_notes` (Phase 4)
Saved notes that the student can reopen and edit.

| Column | Notes |
| --- | --- |
| `id`, `title` | The title can be renamed |
| `mode` | `overview`, `chapter` or `topic` |
| `length` | `short` or `detailed` |
| `document_ids_json` | The PDFs the notes came from |
| `body_json` | Sections (overview, key points, definitions, simple explanations, chapters), each with its sources. An edit must keep at least one source per item. |
| `created_at`, `updated_at` | |

### `mock_exams` and `mock_exam_attempts` (Phase 4)
`mock_exams` stores a generated paper in `payload_json`: questions, correct answers, explanations, model answers and sources. The student never receives these before submitting.

`mock_exam_attempts` has one row per timed attempt: `exam_id` (references `mock_exams.id`, `ON DELETE CASCADE`), `started_at`, `deadline` (the server's end time), `submitted_at` (empty until submitted), `auto_submitted`, `late`, `total_mcq`, `correct`, `percent`, and `answers_json` (the answers the student gave). The server grades each submission. A second submission is refused.

### `flashcard_reviews` (Phase 4)
One spaced-repetition record per flashcard: `deck_id` (references `study_sets.id`, `ON DELETE CASCADE`), `card_index`, `status` (`new`, `known` or `need_practice`), `ease_factor` (starts at 2.5, never below 1.3), `interval_days`, `repetitions`, `due_date` (indexed) and `last_reviewed_at`. Unique `(deck_id, card_index)`.

### `revision_plans` (Phase 4)
Revision tasks for a flashcard deck, due on days 1, 3, 7 and 14. Columns: `deck_id` (`ON DELETE CASCADE`), `title`, `due_date`, `day_offset`, `completed`, `completed_at`.

### `saved_questions` (Phase 4)
Exam or mock questions the student saved for revision: `kind` (`short`, `long` or `mcq`), `question`, `answer`, `sources_json`, `created_at`.

### `mind_maps` (Phase 5)
A saved mind map: `title`, `document_ids_json`, `tree_json` (the centre, branches, subtopics and the sources of each node), and timestamps.

### `research_reports` (unused)
Created by migration `0002` for an earlier Research Assistant, which has been removed. No feature uses this table. It is kept, not deleted, so existing data (if any) is never lost. It is empty in the current database.
