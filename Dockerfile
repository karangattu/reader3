# ---- Stage 1: build deps ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Install only runtime-required system libs for PyMuPDF
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmupdf-dev libfreetype6-dev libjpeg-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim

WORKDIR /app

# Minimal runtime libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmupdf-dev libfreetype6 libjpeg62-turbo zlib1g && \
    rm -rf /var/lib/apt/lists/* && \
    adduser --disabled-password --gecos "" reader3

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY server.py reader3.py ai_service.py semantic_search.py user_data.py ./
COPY templates/ templates/

# Create data volume mount point
RUN mkdir -p /data/books && chown reader3:reader3 /data/books

USER reader3

ENV BOOKS_DIR=/data/books \
    READER3_BOOKS_DIR=/data/books \
    LOG_LEVEL=info \
    HOST=0.0.0.0 \
    PORT=8123 \
    WEB_CONCURRENCY=2 \
    IO_WORKERS=4 \
    MAX_UPLOAD_MB=200 \
    PYTHONUNBUFFERED=1

EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8123/health')" || exit 1

CMD ["python", "-m", "uvicorn", "server:app", \
     "--host", "0.0.0.0", \
     "--port", "8123", \
     "--workers", "2", \
     "--timeout-keep-alive", "30", \
     "--limit-concurrency", "100", \
     "--log-level", "info"]
