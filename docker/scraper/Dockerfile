# One image for the Celery worker, Beat and the one-shot migrate service.
# Build from the repo root (docker-compose.yml does this).
FROM python:3.13-slim

RUN pip install --no-cache-dir "uv==0.13.6"

WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first: code changes then don't reinstall them or Chromium
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/
COPY scraper/pyproject.toml scraper/
RUN uv sync --locked --no-dev --no-install-workspace
RUN playwright install --with-deps chromium

COPY alembic.ini ./
COPY backend backend
COPY scraper scraper
RUN uv sync --locked --no-dev

# Chromium opens untrusted pages, so nothing in this container runs as root
RUN useradd --create-home lakshya
USER lakshya
