"""Himalayas remote jobs, from its public API: https://himalayas.app/docs/remote-jobs-api

Searching with country=Nepal returns only jobs open to people in Nepal, 20 to a search.
Its docs page through results with page=2, but robots.txt disallows "/jobs*&page=", so we
never page. We run one search per kind of job instead, which robots.txt allows and the docs
recommend over walking the whole feed. Results overlap; the pipeline keeps each job once.

Conditions of use (docs/sources.md): every Apply link must be the entry's applicationLink,
Himalayas is shown as the source, and its jobs are never passed on through feeds or
JobPosting structured data.
"""

import json
from html import unescape
from urllib.parse import quote

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import FeedScraper, ListingPage
from lakshya_scraper.scrapers.feed_fields import day_from_epoch, salary_text
from lakshya_scraper.scrapers.html import experience_line, html_to_text

SEARCH_URL = "https://himalayas.app/jobs/api/search?country=Nepal&sort=recent"
_ROLES = [
    "software engineer", "backend", "frontend", "full stack", "python", "javascript", "react",
    "node", "java", "php", "golang", "flutter", "mobile developer", "android", "ios", "devops",
    "cloud", "data engineer", "data analyst", "data scientist", "machine learning", "qa",
    "security", "wordpress", "designer", "product manager", "project manager", "marketing",
    "seo", "content writer", "sales", "customer support", "virtual assistant", "accountant",
    "finance", "recruiter", "human resources", "operations", "business analyst", "teacher",
    "translator", "intern",
]  # fmt: skip
_SEARCHES = [
    f"{SEARCH_URL}&seniority=Entry-level",  # first: what most of our users look for
    *(f"{SEARCH_URL}&q={quote(role)}" for role in _ROLES),
]
_NEPAL_TIME_ZONE = 5.75  # UTC+5:45


class HimalayasScraper(FeedScraper):
    slug = "himalayas"
    min_hours_between_runs = 20  # its data refreshes once a day, so a second run finds nothing

    def first_listing_url(self) -> str:
        return _SEARCHES[0]

    def parse_listing(self, html: str, url: str) -> ListingPage:
        following = _SEARCHES.index(url) + 1
        next_url = _SEARCHES[following] if following < len(_SEARCHES) else None
        return ListingPage(self.items(json.loads(html).get("jobs") or []), next_url)

    def parse_entry(self, entry: dict) -> RawJob | None:
        countries = entry.get("locationRestrictions") or []
        zones = entry.get("timezoneRestrictions") or []
        if (countries and "Nepal" not in countries) or (zones and _NEPAL_TIME_ZONE not in zones):
            return None

        description = html_to_text(entry.get("description") or "")
        return RawJob(
            source_slug=self.slug,
            external_id=entry["guid"],
            url=entry["applicationLink"],
            title=unescape(entry["title"]),
            company=unescape(entry["companyName"]),
            location="Remote",
            salary=salary_text(
                entry.get("minSalary"),
                entry.get("maxSalary"),
                entry.get("currency"),
                entry.get("salaryPeriod"),
            ),
            experience=experience_line(description) or ", ".join(entry.get("seniority") or []),
            deadline=day_from_epoch(entry.get("expiryDate")),
            posted=day_from_epoch(entry.get("pubDate")),
            description=description,
        )
