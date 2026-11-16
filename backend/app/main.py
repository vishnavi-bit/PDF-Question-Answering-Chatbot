"""
FastAPI application entry point.

Run locally:   uvicorn app.main:app --reload --port 8000   (from the backend folder)
Swagger UI:    http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import chat, documents, history, study, study_export, study_tools, upload
from app.core.config import get_settings
from app.database import init_db as db_init
from app.database.connection import engine
from app.services import llm_service, ocr_service
from app.services.llm_service import LLMError
from app.services.study_context import StudyError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    db_init.init_db()
    yield


settings = get_settings()

app = FastAPI(
    title="AI PDF Question Answering Chatbot API",
    version="1.0.0",
    description="Upload PDFs, ask questions, and get answers with page-level citations (RAG + Google Gemini).",
    lifespan=lifespan,
)

allowed_origins = sorted({settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"})
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Accept"],
)

api = APIRouter(prefix="/api")
api.include_router(upload.router)
api.include_router(documents.router)
api.include_router(chat.router)
api.include_router(history.router)
api.include_router(study.router)
api.include_router(study_tools.router)
api.include_router(study_export.router)


@api.get("/health", tags=["system"])
def health() -> dict:
    database_ok = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
    return {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "error",
        "gemini_api_key_configured": llm_service.is_configured(),
        "gemini_model": settings.gemini_model,
        "gemini_status": llm_service.breaker_status(),
        "embedding_model": settings.embedding_model,
        "ocr": ocr_service.status(),
    }


app.include_router(api)


@app.exception_handler(LLMError)
async def gemini_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    # Gemini problems (quota, key, timeout, outage) carry a message written for the user.
    logger.warning("Gemini error on %s %s: %s", request.method, request.url.path, exc.code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.exception_handler(StudyError)
async def study_error_handler(request: Request, exc: StudyError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the details for the developer, but never show internal errors to the user.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred. Please try again."})


# ---------------------------------------------------------------------------
# Serve the built React app (used by the Docker image). In local development
# the Vite dev server serves the frontend instead, so this part is skipped.
# ---------------------------------------------------------------------------
static_dir = settings.static_dir
if (static_dir / "index.html").exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (static_dir / full_path).resolve()
        if full_path and static_dir.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
