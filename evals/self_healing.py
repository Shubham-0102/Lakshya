"""Does self-healing really work? A real model repairs recipes broken by a fake redesign.

Each site's saved pages get their class names renamed, so its working recipe stops matching,
as it would the day a site changes its layout. The jobs on the pages stay the same. Then
relearn() repairs the recipe with a real model. Scored against what the hand-written scraper
reads from the original pages, so the score can only be high if the same data comes back.
No job site is contacted.

    uv run python evals/self_healing.py gemini-3.6-flash
"""

import logging
import sys
import time

from recipe_accuracy import SITES, Score, read, score_job, score_listing

from lakshya_backend.config import get_settings
from lakshya_scraper.llm import Llm, LlmError, gemini_client, gemini_sender
from lakshya_scraper.recipes import Recipe, RecipeScraper
from lakshya_scraper.recipes.learn import LearnFailed, relearn

# What each site's redesign renames: old name -> new name
REDESIGNS = {
    "f1soft": {
        "features-job": "vacancy-card",
        "location-div": "place",
        "job-content": "posting-body",
        "fs-4": "headline",
    },
    "jobsnepal": {
        "card-body": "opening",
        "job-title": "role-name",
        "icon-location4": "pin",
        "apply-deadline": "closes-on",
        "job-posted-on": "published-on",
        "div-job-details": "posting",
    },
    "leapfrog": {"vaccancy__infos": "role-card"},
}


def redesign(html: str, site: str) -> str:
    for old, new in REDESIGNS[site].items():
        html = html.replace(old, new)
    return html


class SavedSite:
    """Serves the redesigned listing at its address, and at each job's address the one saved
    job page with that job's title on it, as a real site would show."""

    def __init__(self, listing_url: str, listing: str, job: str, job_title: str, titles: dict):
        self.listing_url, self.listing, self.job = listing_url, listing, job
        self.job_title, self.titles = job_title, titles

    def fetch(self, url: str, wait_for: str | None = None, settle_ms: int = 0) -> str:
        if url == self.listing_url:
            return self.listing
        return self.job.replace(self.job_title, self.titles.get(url) or self.job_title)

    def fetch_text(self, url: str) -> str:
        return self.fetch(url)


def trial(site, hand_written, name, url, item, llm) -> tuple[bool, Score]:
    score = Score()
    listing_html, job_html = read(site, "listing.html"), read(site, "job.html")
    new_listing = redesign(listing_html, site)
    new_job = redesign(job_html, site)
    old_recipe = Recipe.model_validate_json(read(site, "recipe.json"))
    stale = RecipeScraper(site, url, old_recipe)

    hand = hand_written()
    expected_listing = hand.parse_listing(listing_html, url)
    expected_job = hand.parse_detail(job_html, item)
    titles = {posting.url: posting.title for posting in expected_listing.items}
    fake_site = SavedSite(url, new_listing, new_job, expected_job.title, titles)

    print(f"  {site}: old recipe now finds {len(stale.parse_listing(new_listing, url).items)} jobs")
    started = time.monotonic()
    try:
        recipe = relearn(fake_site, llm, name, stale, lambda posting: True)
    except (LearnFailed, LlmError) as error:
        print(f"  {site}: could not repair: {error}")
        score.add(f"{site}.repaired", True, False)
        return False, score

    print(f"  {site}: repaired in {time.monotonic() - started:.0f}s")
    healed = RecipeScraper(site, url, recipe)
    score_listing(score, site, expected_listing, healed.parse_listing(new_listing, url))
    score_job(score, site, expected_job, healed.parse_detail(new_job, item))
    return True, score


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="    %(message)s")
    for noisy in ("httpx", "httpcore", "google_genai", "google"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = get_settings()
    model = sys.argv[1] if len(sys.argv) > 1 else settings.gemini_models.split(",")[0]
    client = gemini_client(settings.gemini_api_key)
    llm = Llm(gemini_sender(client, timeout_seconds=200), [model], attempts=2)

    repaired, total = 0, Score()
    print(model)
    for site in SITES:
        healed, score = trial(*site, llm)
        repaired += healed
        total.correct += score.correct
        total.total += score.total
        total.misses += score.misses

    print(f"\nRepaired {repaired} of {len(SITES)} sites")
    print(f"Fields read correctly after repair: {total.correct}/{total.total}")
    for miss in sorted(set(total.misses)):
        print(f"    missed {miss}")


if __name__ == "__main__":
    main()
