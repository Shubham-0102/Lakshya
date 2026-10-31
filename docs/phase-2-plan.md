# Phase 2 plan: Smart scraping (weeks 4–6)

**Status: proposed, not yet approved.** Each task still gets its own detailed plan and approval before any code is written.

## Done when
- 10+ sources are enabled, each with a compliance review in `docs/sources.md`.
- The AI learns a page once and saves a recipe; later runs use it with plain code and no AI call.
- A source whose layout changes repairs itself: the run notices, re-learns the page, checks the new recipe, and saves it.
- The same job on several sites is one row with several links back.
- **Gate: 1,000+ clean jobs** in the database.
- The parsing, recipe, self-healing and deduplication tests pass without network access or an API key.

## Key decisions
1. **A recipe is data, not code.** It is JSON stored in `sources.recipe` (migration 0002): CSS selectors for the listing and for each `RawJob` field. Our own interpreter runs it. The AI never writes code that gets executed.
2. **Recipes plug into the existing contract.** `RecipeScraper` implements `first_listing_url`, `parse_listing` and `parse_detail`, so `scrape()`, cleaning, saving and health don't change.
3. **Never trust a recipe until it has been run.** A learned recipe is run on the page it came from and must produce a title, company and link for most items before it is saved. If that fails, the old recipe stays and the source is marked degraded.
4. **Pages are untrusted input to the AI.** A job page could contain text aimed at the model, so the AI gets no tools and can only return a recipe that matches a fixed schema. Check 3 applies to whatever it returns.
5. **Self-healing has limits.** It triggers on what the pipeline already detects (zero jobs, most pages failing) plus a new check for required fields going missing. It re-learns once per run, so a broken site can't run up a bill.
6. **The hand-written scrapers stay** as the baseline. Comparing a learned recipe with the hand-written scraper on the same pages gives a real accuracy number and a realistic way to test self-healing.
7. **Feeds don't use AI.** A remote job board with an official feed gets a small hand-written mapper to `RawJob`, still through `PoliteFetcher`, and we follow its attribution rules. Using the feed instead of scraping is the plan's own rule.
8. **One small LLM wrapper,** `llm.py`, using the official Anthropic SDK and structured output. It logs tokens and cost for every call, which gives us the "cost per job" metric. Default model: `claude-opus-5-5` ($4 / $20 per million input / output tokens).
9. **Deduplication is hand-written and explainable.** Candidates are found by normalized company, then compared on title similarity (`pg_trgm`), location and description. Thresholds are tuned on labelled pairs from our own data. Uncertain matches stay separate: a duplicate is annoying, but merging two different jobs loses one.

## Sources
Only 3 sources are enabled today. On 2026-10-31 they listed 179 jobs and the database held 164, growing by about 13 a day (38 new in 3 days). At that rate they alone would need about 2 months to reach 1,000, so the gate depends on new sources. Everything in this table comes from third-party listings and **must be confirmed on each site's own terms in task 1.**

| Candidate | Type | What we know so far |
| --- | --- | --- |
| Remote OK | Feed | Public API, about 100 newest jobs; link back and name the source |
| Jobicy | Feed | Public API, recent jobs; credit it and send applicants to the original job |
| Arbeitnow | Feed | Public API; link back appreciated; mostly Europe |
| We Work Remotely | Feed | Publishes RSS feeds |
| ReliefWeb | Feed | UN OCHA service with an API; may require a pre-approved app name; can filter to Nepal |
| Himalayas | Feed | Reportedly bars republishing on third-party job sites: likely blocked |
| Remotive | Feed | Sources conflict on whether aggregators are allowed: blocked unless its terms clearly allow it |
| CloudFactory | Career page | Backup from the Phase 1 review; Workable's terms not yet checked |
| More Nepali companies, banks, NGOs | Career pages | To be found. Each adds few jobs, but they are the most relevant to our users. These are what recipes are for. |
| Blocked portals | Portals | Only if they reply to the permission emails |

## Schema
- `sources.recipe` (JSONB, nullable) and `sources.recipe_learned_at`: migration 0002.
- Enable `pg_trgm` and add a trigram index on `jobs.normalized_title`.
- `job_sources` already allows several links per job, so deduplication needs no new table.

## Tasks
| # | Task | Needs |
| --- | --- | --- |
| 1 | Source review (no code); **stop for approval of the new sources** | Your approval |
| 2 | Feed support and the approved feeds | Task 1 |
| 3 | Recipe format and interpreter, tested on fixtures | Nothing |
| 4 | LLM wrapper and migration 0002 | API key |
| 5 | Learn step with validation | API key |
| 6 | Self-healing, tested by breaking fixtures on purpose | API key for a real trial; tests use a fake model |
| 7 | New career pages through recipes | Task 1, API key |
| 8 | Cross-source deduplication, plus `reclean` for jobs with several sources | Labelled pairs from our data |
| 9 | Hand-checked accuracy sample and a metrics script | Your time: checking the sample by hand |
| 10 | README and `CLAUDE.md`, confirm the gate | Enough scheduled runs |

**Not in Phase 2:** CV upload, embeddings, matching, alerts, web app pages, scam flags, tracing beyond the cost log.

## Cost
Estimate, to be replaced by measured numbers from the cost log: a learn call of about 30,000 input and 5,000 output tokens costs about $0.22. With about 20 sources, 2 page types each and some retries, Phase 2 should cost under $10. Normal runs cost nothing because they make no AI calls.
