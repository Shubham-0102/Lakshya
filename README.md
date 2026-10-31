# Lakshya

An AI job agent for Nepal. Lakshya (लक्ष्य, "goal") collects jobs from Nepali job portals, company career pages and remote job feeds, cleans and deduplicates them, matches them to your CV, and alerts you to the ones that fit, with reasons.

> Work in progress. Phase 1 is done: three sources are scraped twice a day and stored in one clean format. AI extraction, matching and alerts come in later phases (see `PLAN.md`).

## Repository layout

| Folder | Contents |
| --- | --- |
| `backend/` | FastAPI app, database models and migrations |
| `scraper/` | Scrapers, cleaning, deduplication and scheduled tasks |
| `evals/` | Hand-checked samples and evaluation scripts |
| `frontend/` | Next.js + TypeScript web app |
| `docs/` | Plans and design notes |

## Run it locally

Requires [Docker](https://docs.docker.com/get-docker/). The Python and frontend steps also need [uv](https://docs.astral.sh/uv/) and Node.js 20+.

```bash
# 1. Settings (once)
cp .env.example .env

# 2. Everything that runs in Docker: Postgres, Redis and the scheduled scraper
docker compose up -d --build
docker compose ps -a
```

`docker compose ps -a` should show `db` and `redis` healthy, `worker` and `beat` running, and `migrate` exited with code 0. `migrate` creates the tables and loads `scraper/sources.yaml`, then stops.

That is all scheduled scraping needs: jobs are collected at 06:00 and 18:00 Nepal time for as long as the containers are running. The first build takes a few minutes because it installs Chromium.

```bash
# 3. Python packages and a headless browser, for tests and the commands below
uv sync
uv run playwright install chromium            # once (on Linux, add --with-deps if system libraries are missing)
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

### Scheduled scraping

Celery Beat wakes up at 06:00 and 18:00 (Asia/Kathmandu) and queues one task per enabled, approved source. The Celery worker runs at most two at once, and a Redis lock stops two runs of the same source from overlapping. A failed run is not retried: the next scheduled run is the retry, and the source's health shows what went wrong.

```bash
docker compose logs -f worker                 # watch runs as they happen
docker compose logs -f beat                   # see when Beat queues them
docker compose exec -T db psql -U lakshya -d lakshya -c \
  "select slug, health_status, failure_count, last_run_at from sources where enabled"
docker compose exec worker celery -A lakshya_scraper.celery_app call lakshya_scraper.tasks.dispatch_scrapes   # run all sources now
docker compose up -d --build worker beat      # after changing scraper code
```

### Scrape by hand

```bash
uv run python -m lakshya_scraper run jobsnepal --dry-run --limit 3   # fetch + clean 3 jobs, save nothing
uv run python -m lakshya_scraper run jobsnepal                # real run: saves new jobs
```

Sources: `jobsnepal`, `f1soft`, `leapfrog` (see `docs/sources.md` for why these three). Every request
checks robots.txt, waits at least 5 seconds per site, and identifies itself as `Lakshya/0.1`. A second
run only reads the listing pages: jobs already stored are not fetched again. If a scheduled run of that source is in progress, the command stops with "already being scraped".

### Re-clean stored jobs

Every job keeps its raw text, so fixes to the cleaning rules can reach jobs saved earlier without visiting the sites again:

```bash
uv run python -m lakshya_scraper reclean --dry-run   # show what would change, save nothing
uv run python -m lakshya_scraper reclean             # apply it
```

Jobs that cleaning would now skip are listed, not deleted.

Postgres and Redis use ports 5433 and 6380, not the defaults, so they don't clash with a Postgres or Redis already installed on your machine. Change them in `.env`.

Useful commands:

```bash
docker compose exec db psql -U lakshya -d lakshya    # SQL shell
docker compose exec redis redis-cli                  # Redis shell
docker compose logs -f db                            # follow one service's logs
docker compose down                                  # stop (data is kept)
docker compose down -v                               # stop and delete all data
```

See `PLAN.md` for the full project plan.
