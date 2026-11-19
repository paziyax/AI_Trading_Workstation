# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 - build the Next.js static export
# ---------------------------------------------------------------------------
FROM node:24-alpine AS frontend

WORKDIR /app

# Next.js writes its static export to ./out (output: "export").
ENV NEXT_TELEMETRY_DISABLED=1

# Install dependencies from the lockfile first so this layer stays cached.
# npm ci requires frontend/package-lock.json to be committed.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - Python runtime (FastAPI + static export), no build tooling
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# uv binary from the official image; avoids a pip bootstrap layer.
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependency-only layer. --no-install-project is required here because the
# project package (app/) is copied in the next layer; without it hatchling
# would fail trying to build the wheel from an incomplete source tree.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv

# Application source (app/, db/, tests/), then install the local project into
# the already-populated virtualenv. Dev extras stay out of the image.
COPY backend/ ./
RUN uv sync --frozen --no-dev \
    && rm -rf /root/.cache/uv

# Static export produced by stage 1.
COPY --from=frontend /app/out ./static

# Runtime SQLite directory. It is a named volume at runtime; appuser must own it.
# Deliberately /app/data, not /app/db: backend/db/ (schema.sql, seed.sql) is copied
# to /app/db and the volume must not shadow it.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data

ENV PATH="/app/.venv/bin:${PATH}" \
    STATIC_DIR=/app/static \
    FINALLY_DB_PATH=/app/data/finally.db

EXPOSE 8000

USER appuser

# No curl in the slim image: probe /api/health with the stdlib instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
