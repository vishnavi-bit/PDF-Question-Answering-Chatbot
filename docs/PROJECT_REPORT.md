# AI PDF Chatbot and Study Assistant: final project report

Single-user, local application. No login. Gemini is used for generation; your PDFs and vector index stay on this computer.

## 1. URLs and how to run (Windows PowerShell)

| What | Address |
| --- | --- |
| App (frontend, development) | http://localhost:5173 |
| API (backend) | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/health |

Backend (from the project folder):

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Frontend, in a second PowerShell window:

```powershell
cd frontend
npm run dev
```

Or in VS Code: **Ctrl+Shift+P → Tasks: Run Task → Run Full Project** (also **Ctrl+Shift+B**). **Stop Servers** stops only this project's servers.

Tests and build:

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend; npx vitest run; npx vite build
```

Optional browser checks (need Chrome installed; the app must be running): `node scripts/accessibility-responsive-check.mjs`, `node scripts/simplified-ui-check.mjs`, `node scripts/extraction-browser-check.mjs`, and `node scripts/chat-browser-check.mjs`. Set `BASE_URL` to the app address.

Docker (optional): `docker compose up --build`, then http://localhost:8000. The port is bound to this computer only (`127.0.0.1`).

## 2. Feature status by phase

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Foundation: Alembic baseline, dark mode, backups before database changes | Done, validated |
| 1 | Gemini reliability: retries, cooldown, caching, de-duplication, clear errors | Done, mock-tested. Live calls blocked by the free-tier quota |
| 2 | Chat: streaming answers, citations, regenerate, search, copy | Done, browser-tested |
| 3 | Advanced retrieval: hybrid keyword + semantic search, reranking with fallback, duplicate removal, answer verification, "couldn't find" wording | Done, tested. Live reranking not verified (quota) |
| 4 | Study assistant: notes, quizzes (difficulty), flashcards with spaced repetition, timed mock exams with auto-submit, saved questions, learning path, revision planner | Done, tested and browser-checked with mocked Gemini |
| 5 | Mind maps (grounded, zoom/pan, save/reopen) and PDF exports | Done, tested and browser-checked with mocked Gemini |
| 6 | Research Assistant (paper summaries, comparison, grounded questions, saved reports) | Built, then removed on request: the project now contains only the PDF Chatbot and the Study Assistant |
| 7 | pdfplumber tables (searchable, with page numbers), OCR detection only, large-PDF limits, empty pages and extraction errors | Done, tested, upload browser-checked |
| 8 | Security review, accessibility, responsive layout, UI consistency, documentation | Done (this report) |

## 3. Key features

- Upload several PDFs; select one, several or all for every feature. Duplicate files are indexed once.
- Chat with cited answers, streaming, regenerate, search of conversation history.
- Hybrid retrieval with answer verification; answers the PDFs do not support say so.
- Study tools: notes, quizzes, flashcards (SM-2 schedule), mock exams with a server-side timer, saved questions, learning path built only from recorded data.
- Mind maps; PDF exports of notes, quizzes, results, flashcards, questions, mock exam papers and results, saved questions, mind maps.
- Dark and light themes; keyboard and screen-reader labels; responsive layout.

## 4. Important files

| Area | Files |
| --- | --- |
| Backend app | `backend/app/main.py`, `backend/app/api/*.py`, `backend/app/services/*.py`, `backend/app/database/*.py` |
| New services | `hybrid_search.py`, `keyword_index_service.py`, `rerank_service.py`, `verification_service.py`, `revision_service.py`, `study_tools_service.py`, `mind_map_service.py`, `pdf_export_service.py`, `ocr_service.py` |
| Migrations | `backend/alembic/versions/0001_baseline.py`, `0002_study_upgrade.py`, `0003_document_extraction.py` |
| Frontend pages | `frontend/src/pages/Chat.jsx`, `Study.jsx`, `Home.jsx`, `History.jsx` |
| Study UI | `frontend/src/components/study/*.jsx` |
| Tests | `backend/tests/` (phases 3 to 8), `frontend/src/**/__tests__/` |
| Browser checks | `frontend/scripts/*.mjs` |
| VS Code tasks | `.vscode/tasks.json`, `.vscode/scripts/*.ps1` |
| Documentation | `README.md`, `docs/*.md` |

## 5. New packages

| Package | Purpose | Where |
| --- | --- | --- |
| `google-genai` | Gemini API | backend requirements |
| `alembic` | Database migrations | backend requirements |
| `rank_bm25` | Keyword (BM25) search | backend requirements |
| `reportlab` | PDF export | backend requirements |
| `pdfplumber` | Table extraction | backend requirements |
| `playwright-core` (dev) | Browser checks, uses installed Chrome | frontend devDependencies |
| `axe-core` (dev) | Automated accessibility checks | frontend devDependencies |

## 6. Migrations and backups

| Revision | Change | Data effect |
| --- | --- | --- |
| `0001_baseline` | Original tables, created only if missing | None |
| `0002_study_upgrade` | New study and research tables | Adds tables only |
| `0003_document_extraction` | `documents.table_count`, `documents.pages_without_text` | Adds columns with default 0 |

Before each migration the app copies `app.db` to `backend/data/backups/` (`auto-before-migration-*.db`). Manual backups were also taken before phases 0, 3 and 4 (`backend/data/backups/pre-phase*`). Downgrades are no-ops, so they never delete data.

## 7. Test results (final run)

| Suite | Result |
| --- | --- |
| Backend (pytest) | 380 passed, 2 skipped (the 2 skips need `RUN_REAL_MODEL=1`) |
| Frontend (Vitest) | 145 tests passed (19 files) |
| Production build (`vite build`) | Succeeds |
| Phase 8 accessibility and responsive check | 35 of 35 passed |
| Simplified Study browser check (mocked Gemini parts) | see the final run |
| Upload and extraction browser check (no Gemini) | 5 of 5 passed |
| Chat browser check (Phase 2) | 27 of 27 passed (earlier run) |


## 8. Accessibility, responsive and UI consistency results

- axe-core (WCAG 2.0 and 2.1, levels A and AA) on the five main pages, light and dark, desktop and phone: no serious or critical problems after fixes. The fixes raised the contrast of small grey labels in light mode and of orange status text in dark mode.
- No horizontal page scroll at tablet (768×1024), phone (390×844) or landscape phone (844×390) sizes.
- Light and dark themes use the same design tokens.

## 9. Security review (Phase 8)

Checked and found acceptable:

- Uploads: file type is checked from the file content (not only the name), size is limited, empty files are refused, filenames are cleaned of path parts.
- Files are only served from the upload folder; a stored path outside it returns 400.
- The Gemini key is read from the backend environment (`backend/.env`, which git ignores) and never appears in responses. Tests check this.
- Logs record exception types and cache-key prefixes, not PDF text, questions, answers or keys.
- Errors shown to users are short messages; tests check that no traceback reaches the browser.
- The frontend does not use HTML injection (`innerHTML` and raw HTML are not used).
- SQL uses the ORM; no string-built queries.
- Docker port changed to `127.0.0.1:8000:8000`, so other devices on your network cannot reach the app.

Limits (see section 11): the app has no login, so anyone who can reach the port can use it; use it on a trusted computer only.

## 10. Database and data safety

- All schema changes go through Alembic with a backup first.
- Study, mind map and document data are kept on upgrade; no existing rows were removed in any phase.
- Deleting a PDF removes its chunks and vectors from the index. Saved quiz attempts stay in the progress history (as in Phase 2).

## 11. Known limitations

- **Live Gemini was not validated** for the final phases. The free-tier quota was exhausted (HTTP 429) during testing, so reranking, generated quality, mind maps and the mock exam generator were tested only with fake responses. Every mocked browser result is labelled MOCKED.
- Summaries and comparisons only send a sample of each PDF's text (about 12,000 characters for one paper, up to 24,000 for a comparison). Long papers can have sections missed.
- Tables are found only when they have ruling lines.
- OCR is not run. Scanned PDFs are detected and explained; they cannot be searched until a future version adds OCR.
- No login or multi-user support (single-user by design).
- Mind maps depend on Gemini quality; grounding rules remove unsupported items but cannot judge whether a kept point is well summarised.
- Large PDFs (up to 1000 pages) can take minutes to index on a CPU.
- Study timers run in the browser for display; the server decides lateness and grades answers.

## 12. Future improvements

- Live Gemini validation once the quota resets, including a retrieval evaluation on the user's own PDFs.
- OCR with Tesseract for scanned pages (the detection is already in place).
- Table detection for tables without ruling lines.
- Background indexing with progress for large PDFs.
- Optional login if the app is ever shared.
- Replace the baseline migration's model-based table creation with explicit definitions.
- Chunk-level re-ranking and summary quality checks with an evaluation set.

## 13. Backend test run

Final run: 380 passed, 2 skipped. The test files are in `backend/tests/`.
