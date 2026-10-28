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

## Quick start (so far)

Requires [uv](https://docs.astral.sh/uv/) and Node.js 20+.

```bash
uv sync                                               # install all Python packages into .venv
uv run pytest                                         # run tests
uv run uvicorn lakshya_backend.main:app --reload      # API at http://localhost:8000/health
```

See `PLAN.md` for the full project plan.
