"""How well does each model learn recipes? Scored against the hand-written scrapers.

The AI learns each site from its saved pages, then its recipe and the hand-written scraper
read those pages. Listing fields are compared as read; job fields are compared after cleaning,
because that's what gets stored and shown ("Apply before 18 Nov, 2026" and "2026-11-18" are the
same deadline). No job site is contacted. Each model makes at least two calls per site, so
this spends free-tier quota, not money.

    uv run python evals/recipe_accuracy.py                    # the models in GEMINI_MODELS
    uv run python evals/recipe_accuracy.py gemini-3.6-flash   # one model
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from lakshya_backend.config import get_settings
from lakshya_scraper.cleaning import clean
from lakshya_scraper.llm import Llm, LlmError, gemini_client, gemini_sender
from lakshya_scraper.recipes import Recipe, RecipeScraper
from lakshya_scraper.recipes.learn import LearnFailed, Page, learn_job, learn_listing
from lakshya_scraper.scrapers import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.f1soft import F1SoftScraper
from lakshya_scraper.scrapers.jobsnepal import JobsNepalScraper
from lakshya_scraper.scrapers.leapfrog import LeapfrogScraper

FIXTURES = Path(__file__).parent.parent / "scraper" / "tests" / "fixtures"
SITES: list[tuple[str, type[Scraper], str, str, ListingItem]] = [
    (
        "f1soft",
        F1SoftScraper,
        "F1Soft Careers, a group of Nepali companies",
        "https://career.f1soft.com/jobs",
        ListingItem(
            "business-analyst-fonenxt", "https://career.f1soft.com/jobs/business-analyst-fonenxt"
        ),
    ),
    (
        "jobsnepal",
        JobsNepalScraper,
        "JobsNepal, a job board",
        "https://www.jobsnepal.com/jobs",
        ListingItem("144747", "https://www.jobsnepal.com/adminfinance-coordinator-144747"),
    ),
    (
        "leapfrog",
        LeapfrogScraper,
        "Leapfrog Technology's own careers site",
        "https://www.lftechnology.com/careers",
        ListingItem(
            "engineering-staff-manager",
            "https://career.lftechnology.com/o/engineering-staff-manager",
        ),
    ),
]
LISTING_FIELDS = ("external_id", "url", "title", "location")
JOB_FIELDS = (
    "title", "company_name", "location", "is_remote", "salary_min", "salary_max",
    "salary_currency", "experience_min_years", "experience_max_years", "deadline",
)  # fmt: skip
_SAME_TEXT = 0.9  # descriptions may differ in spacing or how far they reach


@dataclass
class Score:
    correct: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    def add(self, name: str, wanted: object, got: object) -> None:
        self.total += 1
        self.correct += wanted == got
        if wanted != got:
            self.misses.append(f"{name}: wanted {str(wanted)[:44]!r}, got {str(got)[:44]!r}")


def read(site: str, name: str) -> str:
    return (FIXTURES / site / name).read_text(encoding="utf-8")


def score_listing(score: Score, site: str, expected, actual) -> None:
    padded = actual.items + [None] * len(expected.items)  # missing postings count as wrong
    for wanted, got in zip(expected.items, padded, strict=False):
        for name in LISTING_FIELDS:
            score.add(f"{site}.listing.{name}", getattr(wanted, name), getattr(got, name, None))
    score.add(f"{site}.listing.count", len(expected.items), len(actual.items))
    score.add(f"{site}.listing.next_page", expected.next_url, actual.next_url)


def score_job(score: Score, site: str, expected, actual) -> None:
    wanted, got = clean(expected), clean(actual)
    for name in JOB_FIELDS:
        score.add(f"{site}.job.{name}", getattr(wanted, name), getattr(got, name, None))
    similarity = SequenceMatcher(None, expected.description, actual.description or "").ratio()
    score.add(
        f"{site}.job.description",
        "same text",
        "same text" if similarity >= _SAME_TEXT else f"{similarity:.0%} alike",
    )


def score_nothing_read(score: Score, site: str, hand, listing_html, job_html, url, item) -> None:
    """A site the model couldn't learn misses every field, not one: it would hide the failure."""
    score_listing(score, site, hand.parse_listing(listing_html, url), ListingPage([]))
    wanted = clean(hand.parse_detail(job_html, item))
    for name in (*JOB_FIELDS, "description"):
        score.add(f"{site}.job.{name}", getattr(wanted, name), None)


def evaluate(model: str, client) -> Score:
    llm = Llm(gemini_sender(client, timeout_seconds=200), [model], attempts=2)
    score = Score()
    for site, hand_written, name, url, item in SITES:
        listing_html, job_html = read(site, "listing.html"), read(site, "job.html")
        hand = hand_written()
        started = time.monotonic()
        try:
            listing = learn_listing(llm, Page(url, listing_html), name)
            job = learn_job(llm, Page(item.url, job_html), item, name)
        except (LearnFailed, LlmError) as error:
            print(f"  {site}: could not learn: {error}")
            score_nothing_read(score, site, hand, listing_html, job_html, url, item)
            continue
        print(f"  {site}: learned in {time.monotonic() - started:.0f}s")
        recipe = RecipeScraper(site, url, Recipe(listing=listing, job=job))
        score_listing(
            score,
            site,
            hand.parse_listing(listing_html, url),
            recipe.parse_listing(listing_html, url),
        )
        score_job(
            score, site, hand.parse_detail(job_html, item), recipe.parse_detail(job_html, item)
        )
    return score


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="    %(message)s")
    for noisy in ("httpx", "httpcore", "google_genai", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = get_settings()
    client = gemini_client(settings.gemini_api_key)
    models = sys.argv[1:] or settings.gemini_models.split(",")
    results = {}
    for model in models:
        print(f"\n{model}")
        results[model] = evaluate(model, client)

    print("\nModel                        Fields correct")
    for model, score in results.items():
        share = score.correct / score.total if score.total else 0
        print(f"{model:<28} {score.correct}/{score.total} ({share:.0%})")
        for miss in sorted(set(score.misses)):
            print(f"    missed {miss}")


if __name__ == "__main__":
    main()
