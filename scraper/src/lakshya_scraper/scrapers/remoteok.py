"""Remote OK remote jobs, from its public feed (the newest 100 or so).

The feed's first element is a legal notice, not a job. Most jobs leave `location` blank; a
filled one usually limits who can apply, so cleaning drops those. Text fields hold HTML
entities ("Sales &amp; Support"), and salaries are yearly USD with 0 meaning "not given".

Conditions of use (docs/sources.md): link back to the job's Remote OK url with a normal
followed link, name Remote OK as the source, and don't use its logo.
"""

import json
from html import unescape

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import FeedScraper, ListingPage
from lakshya_scraper.scrapers.feed_fields import remote_location, salary_text
from lakshya_scraper.scrapers.html import experience_line, html_to_text

FEED_URL = "https://remoteok.com/json"


class RemoteOkScraper(FeedScraper):
    slug = "remoteok"

    def first_listing_url(self) -> str:
        return FEED_URL

    def parse_listing(self, html: str, url: str) -> ListingPage:
        return ListingPage(self.items([entry for entry in json.loads(html) if "id" in entry]))

    def parse_entry(self, entry: dict) -> RawJob | None:
        description = html_to_text(entry.get("description") or "")
        return RawJob(
            source_slug=self.slug,
            external_id=str(entry["id"]),
            url=entry["url"],
            title=unescape(entry["position"]),
            company=unescape(entry["company"]),
            location=remote_location(entry.get("location")),
            salary=salary_text(entry.get("salary_min"), entry.get("salary_max"), "USD", "year"),
            experience=experience_line(description),
            posted=entry.get("date"),
            description=description,
        )
