"""Arbeitnow jobs, from its free public API: https://www.arbeitnow.com/blog/job-board-api

Mostly on-site jobs in Germany, and the API has no remote filter, so only the first few
pages are read and only remote jobs are kept. Pages hold 300 jobs each.

Condition of use (docs/sources.md): a link back to Arbeitnow.com on our platform.
"""

import json
from html import unescape

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import FeedScraper, ListingPage
from lakshya_scraper.scrapers.feed_fields import day_from_epoch, remote_location
from lakshya_scraper.scrapers.html import experience_line, html_to_text

FEED_URL = "https://www.arbeitnow.com/api/job-board-api"
_MAX_PAGES = 5  # the newest jobs; the rest would be many requests for very few remote jobs


class ArbeitnowScraper(FeedScraper):
    slug = "arbeitnow"

    def first_listing_url(self) -> str:
        return FEED_URL

    def parse_listing(self, html: str, url: str) -> ListingPage:
        data = json.loads(html)
        next_url = data["links"].get("next")
        if data["meta"]["current_page"] >= _MAX_PAGES:
            next_url = None
        return ListingPage(self.items(data["data"]), next_url)

    def parse_entry(self, entry: dict) -> RawJob | None:
        if not entry.get("remote"):
            return None
        description = html_to_text(entry.get("description") or "")
        return RawJob(
            source_slug=self.slug,
            external_id=entry["slug"],
            url=entry["url"],
            title=unescape(entry["title"]),
            company=unescape(entry["company_name"]),
            location=remote_location(entry.get("location")),
            experience=experience_line(description),
            posted=day_from_epoch(entry.get("created_at")),
            description=description,
        )
