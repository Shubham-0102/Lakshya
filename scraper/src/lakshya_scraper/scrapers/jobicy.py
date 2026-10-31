"""Jobicy remote jobs, from its public API: https://jobicy.com/jobs-rss-feed

Returns jobs published in the last 7 days, up to 100 a page, with a cursor to the next page.

Conditions of use (docs/sources.md): credit Jobicy, keep its listing URL, never present its
jobs as our own, and call the API at most once an hour.
"""

import json
from html import unescape
from urllib.parse import quote

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import FeedScraper, ListingPage
from lakshya_scraper.scrapers.feed_fields import remote_location, salary_text
from lakshya_scraper.scrapers.html import experience_line, html_to_text

FEED_URL = "https://jobicy.com/api/jobs?count=100"


class JobicyScraper(FeedScraper):
    slug = "jobicy"

    def first_listing_url(self) -> str:
        return FEED_URL

    def parse_listing(self, html: str, url: str) -> ListingPage:
        data = json.loads(html)
        cursor = data.get("nextCursor")
        next_url = f"{FEED_URL}&cursor={quote(cursor, safe='')}" if cursor else None
        return ListingPage(self.items(data.get("jobs") or []), next_url)

    def parse_entry(self, entry: dict) -> RawJob | None:
        description = html_to_text(entry.get("jobDescription") or "")
        return RawJob(
            source_slug=self.slug,
            external_id=str(entry["id"]),
            url=entry["url"],
            title=unescape(entry["jobTitle"]),
            company=unescape(entry["companyName"]),
            location=remote_location(entry.get("jobGeo")),
            salary=salary_text(
                entry.get("salaryMin"),
                entry.get("salaryMax"),
                entry.get("salaryCurrency"),
                entry.get("salaryPeriod"),
            ),
            experience=experience_line(description) or entry.get("jobLevel"),
            posted=entry.get("pubDate"),
            description=description,
        )
