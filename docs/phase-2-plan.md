# Phase 2 plan: Smart scraping (weeks 4–6)

Approved 2026-10-31. Each task still gets its own detailed plan and approval before any code is written.

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
8. **One small LLM wrapper,** `llm.py`, so the provider can change in one place. Phase 2 uses the Gemini API free tier with structured output from a Pydantic schema. Google says to validate the values in application code, which decision 3 already does. The model is a setting, not hard-coded, and the wrapper retries and falls back to another free model when one is busy: in a first test on 2026-10-31, `gemini-3.8-flash` was overloaded (a 503 and timeouts), `gemini-3.6-flash` answered in 11 s, `gemini-3.5-flash-lite` in 2 s, and `gemini-2.5-flash` returned 404 for new users despite being listed as free. Task 5 picks the default by measuring which model makes the best recipes. The wrapper logs tokens for every call, which gives us the "cost per job" metric.
9. **Only public job text goes to a free tier.** Google may use free-tier content to improve its products, human reviewers may read it, and its terms say not to submit personal information. So scripts and styles are stripped and emails and phone numbers removed before a page is sent. **CVs never go to a free tier:** Phase 3 needs a paid API, chosen then.
10. **Deduplication is hand-written and explainable.** Candidates are found by normalized company, then compared on title similarity (`pg_trgm`), location and description. Thresholds are tuned on labelled pairs from our own data. Uncertain matches stay separate: a duplicate is annoying, but merging two different jobs loses one.

## Sources
Reviewed on 2026-10-31; verdicts, conditions and quotes are in `docs/sources.md`. On that date the 3 enabled sources listed 179 jobs and the database held 164, growing by about 13 a day (38 new in 3 days). At that rate they alone would need about 2 months to reach 1,000, so the gate depends on new sources.

| Status | Sources |
| --- | --- |
| Allowed, pending approval | Himalayas, Remote OK, Jobicy, Arbeitnow, ICIMOD, Bajra Technologies |
| Unconfirmed or waiting | We Work Remotely, ReliefWeb |
| Blocked | Remotive, YoungInnovations, Cotiviti, Yarsa Labs, CloudFactory (unclear), Deerwalk, EB Pearls |

Himalayas reports 1,285 jobs open to Nepal, so it could supply most of the gate. Duplicates across feeds aren't removed until task 8, so the gate must be measured after that.

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
Free on the Gemini free tier, if its limits hold. Google doesn't publish the free limits in its docs, so task 4 starts by reading them at `aistudio.google.com/rate-limit`. Limits apply per project, so extra keys don't add quota, and the daily quota resets at midnight Pacific time. About 20 sources with 2 page types each, plus retries, is a few dozen calls in total, and normal runs make no AI calls. If the free tier isn't enough, or a free model's recipes fail validation too often, the wrapper can switch to a paid model.
