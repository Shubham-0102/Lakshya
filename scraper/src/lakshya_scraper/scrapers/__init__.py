"""One scraper per approved source; each turns its site's pages into RawJobs."""

from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper

# slug -> scraper class. The site scrapers are added in Phase 1 task 8.
SCRAPERS: dict[str, type[Scraper]] = {}


def get_scraper(slug: str) -> Scraper:
    if slug not in SCRAPERS:
        raise KeyError(f"no scraper for source {slug!r} (known: {sorted(SCRAPERS)})")
    return SCRAPERS[slug]()


__all__ = ["SCRAPERS", "ListingItem", "ListingPage", "Scraper", "get_scraper"]
