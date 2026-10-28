"""One scraper per approved source; each turns its site's pages into RawJobs."""

from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.f1soft import F1SoftScraper
from lakshya_scraper.scrapers.jobsnepal import JobsNepalScraper
from lakshya_scraper.scrapers.leapfrog import LeapfrogScraper

# slug -> scraper class; one per enabled source in sources.yaml
SCRAPERS: dict[str, type[Scraper]] = {
    F1SoftScraper.slug: F1SoftScraper,
    JobsNepalScraper.slug: JobsNepalScraper,
    LeapfrogScraper.slug: LeapfrogScraper,
}


def get_scraper(slug: str) -> Scraper:
    if slug not in SCRAPERS:
        raise KeyError(f"no scraper for source {slug!r} (known: {sorted(SCRAPERS)})")
    return SCRAPERS[slug]()


__all__ = ["SCRAPERS", "ListingItem", "ListingPage", "Scraper", "get_scraper"]
