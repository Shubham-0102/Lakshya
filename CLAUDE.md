# Lakshya

**Lakshya** (लक्ष्य, "goal" or "target"): a personal AI job agent for Nepal. It scrapes jobs from Nepali job portals, company career pages and remote job feeds, cleans and deduplicates them, matches them to each user's CV, and sends alerts and tailored application kits that the user reviews before applying.

`PLAN.md` is the source of truth for scope, phases, metrics and risks. This file is the short version plus the rules every session must follow. (The project was first called "Nepal Jobs Radar". Use "Lakshya" everywhere: code, user agent, README, repo.)

## About the developer

- CS + AI undergrad building this as a portfolio project for big-tech applications.
- Knows Python, FastAPI, React, PostgreSQL, Redis and Docker.
- Wants to explain every part in interviews: briefly explain each decision (what, why, trade-off) while working.

## Current status

- Phase 1 (Scraping basics): done 2026-10-31. Plan and decisions: `docs/phase-1-plan.md`. Beat was proven with a temporary one-minute schedule; the first run on the real schedule (06:00 Kathmandu, 2026-11-01) still has to be confirmed in `docker compose logs beat` and `sources.last_run_at`.
- Phase 2 (Smart scraping): plan approved 2026-10-31, see `docs/phase-2-plan.md`. Tasks 1 to 6 are done: source review, feeds, recipes (`recipes/`), Gemini wrapper (`llm.py`), learn step (`recipes/learn.py`, CLI `learn`) and self-healing (`run_with_healing`, `relearn`). No enabled source uses a recipe yet, so self-healing has only run on saved pages. Next: rerun the model scores once the quota resets (they were cut short), then task 7, which needs better career pages (ICIMOD's job pages are on Workable, Bajra shows no openings). Show each task's detailed plan and wait for approval. Tasks 4 to 7 use `GEMINI_API_KEY`, which is in `.env` and works (free tier, checked 2026-10-31). Never print or read that value; check it from a script that reports only its format.
- Compliance (`docs/sources.md`): of the job portals, only jobsnepal is allowed; merojob, kumarijob, kantipurjob and ramrojob forbid scraping or reuse in their terms; hamrojob is a parked domain. Company career pages: F1Soft and Leapfrog are allowed.
- Approved sources: jobsnepal, F1Soft, Leapfrog, and the feeds Himalayas, Remote OK, Jobicy, Arbeitnow (all enabled); ICIMOD and Bajra (approved, waiting for recipes in task 7). That's 9; the 10th must come from We Work Remotely (check its feed and terms; it answered 403 on a page) or ReliefWeb (the user must request an appname). The Muse and Working Nomads were reviewed as replacements and are blocked. Each source's conditions of use are in `docs/sources.md`; the web app must follow them.
- Jobicy's scraper was built from its docs and has never run on real data: check its first scheduled run (it answered 429 during the review, so it was held until 2026-11-01).
- The user is sending permission emails to the blocked portals (template in `docs/sources.md`).
- Approved cleaning decisions: jobs people in Nepal can't take are dropped, both on-site jobs abroad and remote jobs limited to other places (changed 2026-10-31; a remote job naming any place except Nepal, Asia or anywhere counts as limited); a salary with no currency is assumed NPR if ≥ 1,000; ambiguous numeric dates are day/month; a year ≥ 2070 means Bikram Sambat.
- Where things live: `cleaning/` (`clean(raw) -> CleanJob | None`, one pure module per field), `fetching/` (hand-written RFC 9309 robots parser, Redis throttle, `PoliteFetcher`), `pipeline.py` (`run_source` → `scrape`), `storage.py`, `reclean.py`, `celery_app.py` (schedule), `tasks.py`, `scrapers/{jobsnepal,f1soft,leapfrog}.py`, `job_format.py` (`RawJob`, `CleanJob`), `docker/scraper/Dockerfile`.
- Dev database on 2026-10-31: 713 jobs (Himalayas 459, jobsnepal 137, Remote OK 64, Arbeitnow 26, F1Soft 20, Leapfrog 7), all from before cross-source deduplication. Himalayas reports 1,285 jobs for Nepal, but only the first 20 of each role search are reachable (robots.txt forbids `page=`); the user could ask hi@himalayas.app whether API paging is fine.
- Worth checking: job 69's experience text is contradictory ("2+ years , 3 to 5 years"); the parser takes the first value.
- My shell runs on the user's machine in the same folder, so run checks directly instead of asking the user to paste output. Use `docker compose exec -T` (without `-T`, psql opens a pager and the output disappears).
- GitHub: https://github.com/Shubham-0102/Lakshya (remote `origin`). Push only when the user asks. Push with `git -c credential.helper='!gh auth git-credential' push`; there is no global credential helper.
- Update this section whenever a task or phase is completed.

## Commands

Python uses a uv workspace (root `pyproject.toml`; members `backend`, `scraper`). Import names are `lakshya_backend` and `lakshya_scraper`, in src layout (`backend/src/lakshya_backend/`).

```bash
cp .env.example .env                               # once; .env is git-ignored
docker compose up -d --build                       # Postgres+pgvector on localhost:5433, Redis on localhost:6380, migrate, Celery worker + Beat
docker compose up -d --build worker beat           # after changing scraper code: the image holds a copy of it
docker compose logs -f worker                      # watch scheduled runs
docker compose exec worker celery -A lakshya_scraper.celery_app call lakshya_scraper.tasks.dispatch_scrapes   # run all sources now
docker compose exec db psql -U lakshya -d lakshya  # SQL shell (tests use database lakshya_test)
uv sync                                            # install everything into .venv
uv run alembic upgrade head                        # apply migrations to the dev database (the migrate service also does this)
uv run alembic revision --autogenerate --rev-id 0002 -m "..."   # new migration (review it by hand)
uv run python -m lakshya_scraper.sync_sources      # load scraper/sources.yaml into the sources table
uv run pytest                                      # tests (need docker compose up)
uv run python -m lakshya_scraper run <slug> --dry-run --limit 3   # live fetch + clean, saves nothing
uv run python -m lakshya_scraper run <slug>        # real run (jobsnepal ≈ 15 min at 5 s/request)
uv run python -m lakshya_scraper reclean --dry-run # what re-cleaning job_sources.raw would change, saves nothing
uv run python -m lakshya_scraper reclean           # apply it (no network; rejected feed jobs are removed, rejected page jobs only reported)
uv run python -m lakshya_scraper learn <slug> --dry-run   # the AI writes a recipe from the live site; saves nothing
uv run python -u evals/recipe_accuracy.py <model>  # score a model against the hand-written scrapers (saved pages only)
uv run python -u evals/self_healing.py <model>     # a real model repairs recipes broken by a fake redesign
uv run ruff check . && uv run ruff format --check . # lint + format check (CI runs the same)
uv run uvicorn lakshya_backend.main:app --reload   # API, GET /health
uv add --package lakshya-backend <dep>             # add a dependency to one package
cd frontend && npm run dev                         # Next.js 16 (untouched until Phase 4; see frontend/AGENTS.md)
```

- Tests use FastAPI's `TestClient`, which needs `httpx2` (Starlette deprecated `httpx` for it).
- Add a dependency only in the task that needs it.

## Scraper conventions

- Every request to a site goes through `PoliteFetcher.fetch()`; never use httpx/requests/Playwright directly in a scraper.
- A scraper only parses (`first_listing_url`, `parse_listing`, `parse_detail` → `RawJob`). Fetching, cleaning, saving and health live in the pipeline.
- Official feeds use `FeedScraper` (`parse_entry` → `RawJob`, or None for jobs Nepal can't take) and `PoliteFetcher.fetch_text`, and carry whole jobs on `ListingItem.raw`, so no job page is opened. Their test fixtures are hand-written with invented companies.
- Before trusting a feed's size, test its next-page URL against robots.txt: Himalayas' docs use `page=`, but its robots.txt forbids it, so it runs role searches instead. Never route around a robots.txt refusal.
- Terms come first: in a source review, read terms and docs before any feed or job page, and stop contacting a site that answers 403 or 429.
- Put `title`/`location` on `ListingItem` when the listing shows them, so tenders and jobs limited to outside Nepal are skipped without a request.
- Health: a run with a `problem` (zero jobs, listing failed, most job pages failed, 403/429) → `degraded`, then `failing` after 3 runs in a row. Hitting the request limit is not a problem.
- Chromium for Playwright: `uv run playwright install chromium`.
- Schedule: Beat calls `dispatch_scrapes` at 06:00 and 18:00 Asia/Kathmandu; it queues `scrape_source` for each enabled, approved source with a scraper. No automatic retries: the next scheduled run is the retry.
- `run_source` takes the Redis lock (`source_lock`), so CLI and Celery runs can't overlap. `LOCK_TIMEOUT_SECONDS` must stay above the task's `time_limit`.
- `redis` (the Python client) is pinned below 6.5 because stable kombu requires it. Don't raise it until kombu does; a release candidate of kombu is not an acceptable fix.
- In a long sentence, `parse_experience` only counts years with "experience" after them or "minimum"/"at least" before them. "two years of supervised programme" and "more than 40 years of expertise" are not requirements.
- Prefer structured data in this order: JSON-LD (Leapfrog), microdata `itemprop` (JobsNepal), labelled fields (F1Soft), then CSS layout.
- Fixtures are trimmed by hand to the markup a scraper reads (copyrighted pages, public repo). Never commit recruiter names, emails or phone numbers.
- Recipes (`recipes/format.py`) are data, never code, and hold no site address: that comes from `sources`. `RecipeScraper` follows the same contract as a hand-written scraper. `tests/fixtures/*/recipe.json` must read the saved pages to the same result as the hand-written scrapers; that comparison is the accuracy baseline for recipes the AI writes.
- All AI calls go through `Llm.structured()` in `llm.py`, which never logs prompts or replies. 503 and timeouts retry then fall back; 429 and 404 skip to the next model; 400, 401 and 403 stop at once. Only public job text may be sent while on a free tier; CVs never. The free tier allows only 20 requests a day per model, resetting at midnight Pacific (13:45 Nepal time), so check `evals/` runs against that: a full run uses up to 12. The SDK's retries are off in `gemini_client` because it would sleep on Retry-After: `attempts` can't do it (0 becomes 1), so retries are limited to a status code nobody sends. `_within` is the real deadline because the SDK's timeout resets when bytes arrive.
- Learning is two calls, listing then job page, and nothing the AI returns is saved until `check_listing` and `check_job` have run it on the real page. `shrink_page` is the privacy boundary for the free tier: no emails or phones, long text cut. It must keep pagination in `<nav>`, and job pages skip `collapse_runs` because alike table rows hold different fields.
- Self-healing runs the old recipe on the live pages first and re-learns only the half that fails. It keeps a new recipe only if a real run works, spends one round of AI calls per run, and stops once a source is `failing`. Hand-written scrapers never heal themselves.
- Check new cleaning or scraping rules against real data: dry-run the source, then audit what was stored (e.g. every `raw->>'experience'` vs `parse_experience`).

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
