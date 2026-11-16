# One image for the whole app:
#   1. Build the React frontend into static files.
#   2. Run FastAPI, which serves the API under /api and the built frontend at /.

# ---------- Stage 1: build the frontend ----------
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: Python backend + built frontend ----------
FROM python:3.11-slim AS runtime

ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    DATABASE_URL=sqlite:////app/storage/app.db \
    CHROMA_PERSIST_DIRECTORY=/app/storage/chroma_db \
    UPLOAD_DIRECTORY=/app/storage/uploads \
    STATIC_DIRECTORY=/app/frontend/dist \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}

WORKDIR /app/backend

# CPU-only PyTorch is much smaller than the default CUDA build. torch is removed from
# requirements.txt here so pip keeps the CPU build that was installed first.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && grep -v '^torch' requirements.txt > requirements-nodeps-torch.txt \
 && pip install -r requirements-nodeps-torch.txt \
 && rm requirements-nodeps-torch.txt

# Download the embedding model at build time so the first start is fast.
RUN python -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBEDDING_MODEL'])" \
 && chmod -R a+rX /opt/hf-cache

COPY backend/app ./app
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

# Run as a non-root user. Only the storage folder is writable.
RUN useradd --create-home --uid 1000 appuser \
 && mkdir -p /app/storage/uploads /app/storage/chroma_db \
 && chown -R appuser:appuser /app/storage /opt/hf-cache
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
