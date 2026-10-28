# Lakshya

An AI job agent for Nepal. Lakshya (लक्ष्य, "goal") collects jobs from Nepali job portals, company career pages and remote job feeds, cleans and deduplicates them, matches them to your CV, and alerts you to the ones that fit, with reasons.

> Work in progress: Phase 1 (scraping basics). Full setup steps arrive at the end of Phase 1.

## Repository layout

| Folder | Contents |
| --- | --- |
| `backend/` | FastAPI app, database models and migrations |
| `scraper/` | Scrapers, cleaning, deduplication and scheduled tasks |
| `evals/` | Hand-checked samples and evaluation scripts |
| `frontend/` | Next.js + TypeScript web app |
| `docs/` | Plans and design notes |

## Run it locally

Requires [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/) and Node.js 20+.

```bash
# 1. Settings (once)
cp .env.example .env

# 2. Postgres (with pgvector) and Redis in Docker
docker compose up -d
docker compose ps                     # both should show "healthy"

# 3. Python packages, database tables and sources
uv sync
uv run alembic upgrade head                   # create/upgrade the tables
uv run python -m lakshya_scraper.sync_sources # load scraper/sources.yaml into the sources table
uv run pytest                                 # tests use the separate lakshya_test database

# 4. API (leave running in its own terminal)
uv run uvicorn lakshya_backend.main:app --reload

# 5. Frontend (another terminal; it is still the default Next.js page)
cd frontend && npm install && npm run dev
```

| What | Where |
| --- | --- |
| API health check | http://localhost:8000/health |
| API docs (Swagger UI) | http://localhost:8000/docs |
| Frontend | http://localhost:3000 |
| Postgres | `localhost:5433`, database `lakshya` (tests use `lakshya_test`) |
| Redis | `localhost:6380` |

Postgres and Redis use ports 5433 and 6380, not the defaults, so they don't clash with a Postgres or Redis already installed on your machine. Change them in `.env`.

Useful commands:

```bash
docker compose exec db psql -U lakshya -d lakshya    # SQL shell
docker compose exec redis redis-cli                  # Redis shell
docker compose logs -f db                            # follow logs
docker compose down                                  # stop (data is kept)
docker compose down -v                               # stop and delete all data
```

See `PLAN.md` for the full project plan.
