"""One scraper per approved source; each turns its site's pages into RawJobs."""

from lakshya_scraper.scrapers.arbeitnow import ArbeitnowScraper
from lakshya_scraper.scrapers.base import FeedScraper, ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.f1soft import F1SoftScraper
from lakshya_scraper.scrapers.himalayas import HimalayasScraper
from lakshya_scraper.scrapers.jobicy import JobicyScraper
from lakshya_scraper.scrapers.jobsnepal import JobsNepalScraper
from lakshya_scraper.scrapers.leapfrog import LeapfrogScraper
from lakshya_scraper.scrapers.remoteok import RemoteOkScraper

# slug -> scraper class; one per enabled source in sources.yaml
SCRAPERS: dict[str, type[Scraper]] = {
    ArbeitnowScraper.slug: ArbeitnowScraper,
    F1SoftScraper.slug: F1SoftScraper,
    HimalayasScraper.slug: HimalayasScraper,
    JobicyScraper.slug: JobicyScraper,
    JobsNepalScraper.slug: JobsNepalScraper,
    LeapfrogScraper.slug: LeapfrogScraper,
    RemoteOkScraper.slug: RemoteOkScraper,
}


def get_scraper(slug: str) -> Scraper:
    if slug not in SCRAPERS:
        raise KeyError(f"no scraper for source {slug!r} (known: {sorted(SCRAPERS)})")
    return SCRAPERS[slug]()


__all__ = ["SCRAPERS", "FeedScraper", "ListingItem", "ListingPage", "Scraper", "get_scraper"]
