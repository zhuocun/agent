# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

# Install uv from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy lockfiles first for layer caching.
COPY pyproject.toml uv.lock ./

# Install runtime deps only (no dev) into a project-local venv.
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Install the project itself (no deps; already done).
RUN uv sync --frozen --no-dev

EXPOSE 8000

# Start uvicorn. Fly.io sets PORT. Migrations run once per deploy via the Fly
# `[deploy] release_command` (see fly.toml), NOT on every machine boot — so a
# cold start (a fresh deploy, or a Fly-initiated machine stop) doesn't pay
# `alembic upgrade head` against a cold cross-region DB before it can serve the
# first request. `flyctl deploy` runs the release command on a temporary machine
# and only rolls out the app machines once it succeeds.
CMD ["sh", "-c", "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
