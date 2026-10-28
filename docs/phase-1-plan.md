# Phase 1 plan: Scraping basics (weeks 1–3)

Approved 2026-10-28. Each task still gets its own detailed plan and approval before any code is written.

## Done when
- `docker compose up` starts Postgres with pgvector, Redis, a Celery worker and Celery Beat.
- The 3 approved sources are scraped on a schedule and saved into `jobs` in clean form, each with a link back to the original posting.
- Running a scraper a second time creates no duplicates; it only updates `last_seen_at`.
- The parsing, cleaning and deduplication tests pass without network access.
- Someone with a fresh clone can get it running just by following the README.

## Key decisions
1. **uv workspace** for all Python code (`backend`, `scraper`, later `evals`): one lockfile, and the scraper imports the database models instead of copying them.
2. **The backend owns the schema:** SQLAlchemy 2.0 models and Alembic migrations live in `/backend`. The scraper is just another client of the database.
3. **The scraper is synchronous:** Celery tasks are sync, so it uses Playwright's sync API and sync SQLAlchemy with psycopg 3.
4. **Fetching and parsing are separate:** Playwright only fetches the rendered HTML; a pure function turns HTML into a `RawJob` using BeautifulSoup CSS selectors. Tests run on saved HTML files. Phase 2's AI recipes plug into this same parse step.
5. **Structured data first:** read schema.org `JobPosting` JSON-LD when a page has it, and fall back to CSS selectors.
6. **Two job formats:** every scraper outputs a `RawJob` (text exactly as on the page, plus URL and the site's job ID); one `clean()` function turns it into a typed `CleanJob`.
7. **Keep the raw record** as JSONB, so the cleaner can be re-run from the database instead of scraping the sites again.
8. **One shared `PoliteFetcher`** enforces the scraping rules: checks robots.txt before every URL, waits at least 5 s between requests to a site (longer if robots.txt sets `Crawl-delay`) with the timer kept in Redis, sends an honest user agent, retries with increasing waits, stops at a page limit per run, and only opens detail pages for jobs not seen before.
9. **Columns arrive in the phase that needs them:** `recipe` (Phase 2), `embedding` (Phase 3), `scam_score` (Phase 5), each through its own migration.

## Schema
- `sources`: slug (unique), name, base_url, type (portal / career_page / feed), enabled, compliance_status (approved / blocked / pending), compliance_notes, crawl_delay_seconds, health_status (healthy / degraded / failing), failure_count, last_run_at, last_success_at
- `companies`: name, normalized_name (unique), website, verified (defaults to false)
- `jobs`: company_id, title, normalized_title, location, is_remote, salary_min, salary_max, salary_currency, salary_period, salary_text, experience_min_years, experience_max_years, skills (text[]), deadline, description, first_seen_at, last_seen_at
- `job_sources` (link table between jobs and sources): job_id, source_id, external_id, url, raw (JSONB), first_seen_at, last_seen_at, with UNIQUE(source_id, external_id)
- Migration 0001 also runs `CREATE EXTENSION vector`.
- Phase 1 deduplication is exact matching within one source: insert, or update if `(source_id, external_id)` already exists. Fuzzy matching across sources is Phase 2.

## Cleaning
| Field | Must handle |
| --- | --- |
| Title | "Urgent Hiring:", "(2 Positions)", "– Kathmandu"; spacing and capitalization; lowercase `normalized_title` |
| Company | "Pvt. Ltd." / "Private Limited" removed for `normalized_name` |
| Location | Aliases ("KTM", "Kathmandu Valley" → Kathmandu; "Patan" → Lalitpur), remote detection; unknown values kept and logged |
| Salary | "NPR 50,000–70,000/month", "Rs. 50K", "1.5 lakh", "$1,200", "Negotiable" → min, max, currency, period, plus the original text |
| Experience | "2+ years", "1–2 years", "Fresher" → minimum and maximum years |
| Deadline | AD dates, relative dates ("5 days left"), Bikram Sambat dates (converted with `nepali-datetime`) |

## Tasks (one commit each, or more where noted)
1. Repo skeleton
2. Source compliance check (no code); **stop for approval of the 3 sources**
3. Docker Compose: Postgres (pgvector) and Redis
4. Schema and Alembic migrations, plus loading sources from `sources.yaml`
5. Common job format: `RawJob` and `CleanJob`
6. Cleaning, with table-driven tests using real strings
7. `PoliteFetcher` and the `run_source()` pipeline. A run with zero jobs marks the source `degraded`.
8. Three scrapers (one commit each), plus the `--dry-run` CLI
9. Celery and Beat: `dispatch_scrapes` runs twice a day (Asia/Kathmandu time), a Redis lock per source stops overlapping runs, and the worker and Beat run in compose
10. README, then update `CLAUDE.md` with commands and decisions

**Not in Phase 1:** AI extraction, recipes, self-healing, cross-source deduplication, remote job feeds, any API endpoint besides `/health`, frontend pages, embeddings, the user tables, and tracing.

## Settled
- User agent: `Lakshya/0.1 (+https://github.com/Shubham-0102/Lakshya; yadavvshubham0102@gmail.com)`. Repo: https://github.com/Shubham-0102/Lakshya (remote `origin`).
- Sources: see `docs/sources.md`. Of the job portals, only jobsnepal allows it. The other 2 Phase 1 sources are company career pages (option A), Nepali tech companies first.
