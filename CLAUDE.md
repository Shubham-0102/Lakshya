# Lakshya

**Lakshya** (लक्ष्य, "goal" or "target"): a personal AI job agent for Nepal. It scrapes jobs from Nepali job portals, company career pages and remote job feeds, cleans and deduplicates them, matches them to each user's CV, and sends alerts and tailored application kits that the user reviews before applying.

`PLAN.md` is the source of truth for scope, phases, metrics and risks. This file is the short version plus the rules every session must follow. (The project was first called "Nepal Jobs Radar". Use "Lakshya" everywhere: code, user agent, README, repo.)

## About the developer

- CS + AI undergrad building this as a portfolio project for big-tech applications.
- Knows Python, FastAPI, React, PostgreSQL, Redis and Docker.
- Wants to explain every part in interviews: briefly explain each decision (what, why, trade-off) while working.

## Current status

- Phase 1 (Scraping basics): plan approved 2026-10-28. The approved plan, decisions and open questions are in `docs/phase-1-plan.md`.
- Task 1 (repo skeleton) done.
- Task 2 (source compliance check) done: see `docs/sources.md`. Of the job portals, only jobsnepal is allowed; merojob, kumarijob, kantipurjob and ramrojob forbid scraping or reuse in their terms; hamrojob is a parked domain. Company career pages: F1Soft and Leapfrog are allowed.
- Approved Phase 1 sources: jobsnepal, F1Soft careers, Leapfrog careers.
- The user is sending permission emails to the blocked portals (template in `docs/sources.md`).
- Task 3 (Docker Compose) done.
- Task 4 (schema and migrations) done: models in `backend/src/lakshya_backend/db/models.py`, migration 0001, `scraper/sources.yaml` + `sync_sources`.
- Task 5 (common job format) done: `RawJob` and `CleanJob` in `scraper/src/lakshya_scraper/job_format.py`.
- Task 6 (cleaning) done: `scraper/src/lakshya_scraper/cleaning/`, with `clean(raw) -> CleanJob | None` in `clean.py` and one pure module per field. Approved decisions: on-site jobs outside Nepal are dropped (remote ones kept); a salary with no currency is assumed NPR if ≥ 1,000; ambiguous numeric dates are day/month; a year ≥ 2070 means Bikram Sambat.
- Next: task 7 (PoliteFetcher and the `run_source()` pipeline). Show its detailed plan and wait for approval.
- My shell runs on the user's machine in the same folder, so run checks directly instead of asking the user to paste output. Use `docker compose exec -T` (without `-T`, psql opens a pager and the output disappears).
- GitHub: https://github.com/Shubham-0102/Lakshya (remote `origin`). Push only when the user asks. Push with `git -c credential.helper='!gh auth git-credential' push`; there is no global credential helper.
- Update this section whenever a task or phase is completed.

## Commands

Python uses a uv workspace (root `pyproject.toml`; members `backend`, `scraper`). Import names are `lakshya_backend` and `lakshya_scraper`, in src layout (`backend/src/lakshya_backend/`).

```bash
cp .env.example .env                               # once; .env is git-ignored
docker compose up -d                               # Postgres+pgvector on localhost:5433, Redis on localhost:6380
docker compose exec db psql -U lakshya -d lakshya  # SQL shell (tests use database lakshya_test)
uv sync                                            # install everything into .venv
uv run alembic upgrade head                        # apply migrations to the dev database
uv run alembic revision --autogenerate --rev-id 0002 -m "..."   # new migration (review it by hand)
uv run python -m lakshya_scraper.sync_sources      # load scraper/sources.yaml into the sources table
uv run pytest                                      # tests (need docker compose up)
uv run ruff check . && uv run ruff format --check . # lint + format check (CI runs the same)
uv run uvicorn lakshya_backend.main:app --reload   # API, GET /health
uv add --package lakshya-backend <dep>             # add a dependency to one package
cd frontend && npm run dev                         # Next.js 16 (untouched until Phase 4; see frontend/AGENTS.md)
```

- Tests use FastAPI's `TestClient`, which needs `httpx2` (Starlette deprecated `httpx` for it).
- Add a dependency only in the task that needs it.

## Database conventions

- Sync SQLAlchemy 2 + psycopg 3. Alembic settings are in `[tool.alembic]` in `pyproject.toml`; `alembic.ini` is a stub the CLI requires. The URL comes from `.env` via `lakshya_backend.config.Settings`.
- Enums are stored as text + CHECK constraints (`text_enum` in `db/base.py`), not native Postgres enums.
- All constraints are named by the naming convention in `db/base.py`. Tests match on those names.
- Scraping rules live in the schema: `ck_sources_enabled_only_if_approved`, `ck_sources_polite_crawl_delay`.
- Add columns only in the phase that needs them, each with its own migration (`recipe` in Phase 2, `embedding` in Phase 3, `scam_score` in Phase 5).
- DB test fixtures are in the root `conftest.py`: `db_session` (rolled back after each test) and `alembic_cfg`. The fixture wipes `TEST_DATABASE_URL` and refuses databases whose names don't end in `_test`.
- `test_models_match_migrations` fails if a model changes without a migration.

## How the product works

Three layers:
1. **Collect:** a scraper gathers jobs, cleans them into one format, removes duplicates and repairs itself when a site's layout changes.
2. **Understand:** AI parses the CV, scores each job against it with reasons and missing skills, and flags suspicious postings.
3. **Act:** alerts (Telegram, email), a tailored CV and cover letter, an application tracker. The user approves everything before it is sent.

Two pipelines:
- **Collection (scheduled, shared):** sources → scraper (saved extraction recipe, self-heals) → clean + dedupe → Postgres + pgvector
- **Per user (when new jobs arrive):** CV → matcher (embeddings shortlist, then LLM scores and explains) → alerts and application kit → user reviews and submits

Scraper design (Phase 2 onward): the AI learns a page once and saves a reusable recipe of selectors; later runs use the recipe with plain code and no AI call; if a run finds missing fields or zero jobs, the AI re-learns the page and saves a new recipe (self-healing).

## Tech stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js (React) + TypeScript + Tailwind |
| Backend API | FastAPI (Python) |
| Database | PostgreSQL + pgvector |
| Scheduling and background jobs | Redis + Celery + Celery Beat |
| Browsing | Playwright |
| Extraction | Own AI extraction step that produces reusable recipes |
| LLM | Any model API with structured output, behind one small wrapper |
| Embeddings | An embedding model for jobs and CVs |
| Alerts | Telegram Bot API + an email service |
| Deployment | Docker Compose on a small cloud server; frontend on Vercel |
| Tracing | Langfuse or OpenTelemetry, plus structured logs |

## Folder structure (monorepo)

```
/frontend            Next.js + TypeScript: job search, profile, matches, tracker (pages built in Phase 4)
/backend             FastAPI app, database models, migrations
/scraper             Scrapers, cleaning, deduplication, Celery tasks and Beat schedule
/evals               Hand-checked samples and evaluation scripts (extraction accuracy, match quality, scam detection)
docker-compose.yml   PostgreSQL (with pgvector) and Redis
PLAN.md              Full project plan
CLAUDE.md            This file
README.md            Setup steps
```

## Data model

| Table | Stores | Key fields | Phase |
| --- | --- | --- | --- |
| `sources` | Every website the scraper visits | url, type, saved extraction recipe, last success, health status, failure count | 1 |
| `jobs` | One row per unique job | title, company, location, salary range, experience, skills, deadline, description summary, source links, first seen, last seen, scam score, embedding | 1 |
| `companies` | Employers, merged across sources | name, website, verified flag | 1 |
| `users` | Accounts and preferences | email, Telegram id, alert threshold, preferred locations | 3 |
| `profiles` | What the AI learned from each CV | skills, experience years, education, embedding | 3 |
| `matches` | Score of each job for each user | user, job, score, reasons, missing skills, alerted flag | 3 |
| `applications` | The user's tracker | user, job, status, applied date, follow-up date, notes | 4 |

Duplicates are caught by comparing company, title, location and description similarity. A job seen on several sites keeps one row with several source links.

## Non-negotiable rules

### Scraping
- Respect each site's `robots.txt` and terms of service. Skip sites that forbid scraping and ask them for access instead.
- At most one request every few seconds per site, and only during scheduled runs.
- Identify the scraper honestly in its user agent.
- Always link back to the original posting; show a short summary and send users to the source to apply.
- Never collect personal data beyond what the public job posting contains.

### Privacy
- CVs are stored encrypted, deleted when the user asks, and never shared.
- CV text goes to the AI model only for that user's own matching, and the app says so clearly.
- Nothing is ever submitted for a user (no application, no contact with an employer) without their approval.

## Working rules

- Build one phase at a time, in the order in `PLAN.md`. Never build ahead.
- Plan before coding: show the plan for each task and wait for approval before writing code.
- Keep code simple and readable. No scraping frameworks that hide the logic (no Scrapy, Crawlee and the like); extraction and self-healing code is hand-written so it can be explained.
- Write tests for scraping, cleaning and deduplication logic.
- Commit after each working milestone with a clear message.

## Phases (do not start a phase until the previous gate is met)

1. **Weeks 1–3, Scraping basics:** repo, Docker Compose, database, hand-written scrapers for 3 sources with cleaning and scheduled runs.
2. **Weeks 4–6, Smart scraping:** AI extraction with reusable recipes, self-healing, deduplication, 10+ sources. Gate: 1,000+ clean jobs.
3. **Weeks 7–9, Matching:** CV upload and parsing, embeddings, LLM match scores with reasons, Telegram alerts. Gate: 20 classmates using it.
4. **Weeks 10–12, Web app:** job search and filters, profile page, matches page, application tracker.
5. **Weeks 13–16, Agent + launch:** tailored CV and cover letter kit, scam flags, evaluation runs, deployment, demo video. Gate: 100+ users and real numbers for the CV.
