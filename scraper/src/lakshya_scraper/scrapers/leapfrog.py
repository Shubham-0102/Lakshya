"""Leapfrog Technology careers.

Listing: www.lftechnology.com/careers builds its openings with JavaScript; the raw HTML
only has empty placeholders. So the fetcher waits for an opening's link to appear,
which is why this source needs a real browser (Playwright).
Job page: career.lftechnology.com/o/<slug> (hosted on Recruitee) embeds a schema.org
JobPosting as JSON-LD, so every field is read from structured data.
"""

from urllib.parse import urljoin, urlsplit

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.html import (
    country_name,
    experience_line,
    html_to_text,
    json_ld_job_posting,
    parse_html,
    text,
)

LISTING_URL = "https://www.lftechnology.com/careers"
_OPENING_LINK = 'div.vaccancy__infos a[href*="/o/"]'  # "vaccancy" is the site's spelling


class LeapfrogScraper(Scraper):
    slug = "leapfrog"
    listing_wait_for = _OPENING_LINK

    def first_listing_url(self) -> str:
        return LISTING_URL

    def parse_listing(self, html: str, url: str) -> ListingPage:
        items = []
        for opening in parse_html(html).select("div.vaccancy__infos"):
            link = opening.select_one('a[href*="/o/"]')
            if link is None:
                continue
            job_url = urljoin(url, link["href"])
            items.append(
                ListingItem(
                    # The listing only shows the URL, so its slug is the job id
                    external_id=urlsplit(job_url).path.rstrip("/").rsplit("/", 1)[-1],
                    url=job_url,
                    title=text(opening.select_one("h3")),
                    location=text(opening.select_one("p")),
                )
            )
        return ListingPage(items)  # all openings are on one page

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        posting = json_ld_job_posting(parse_html(html))
        if posting is None:
            raise ValueError(f"no JobPosting JSON-LD on {item.url}")
        description = html_to_text(posting.get("description") or "")
        return RawJob(
            source_slug=self.slug,
            external_id=item.external_id,
            url=item.url,
            title=posting.get("title"),
            company=(posting.get("hiringOrganization") or {}).get("name"),
            location=_location(posting),
            salary=_salary(posting.get("baseSalary")),
            experience=experience_line(description),  # JSON-LD has no experience field
            deadline=posting.get("validThrough"),
            posted=posting.get("datePosted"),
            description=description,
        )


def _location(posting: dict) -> str | None:
    """jobLocation (one or several places) -> "Kathmandu, Nepal" or "Pune, India / ..."."""
    places = posting.get("jobLocation") or []
    places = places if isinstance(places, list) else [places]
    names = []
    for place in places:
        address = (place or {}).get("address") or {}
        parts = [address.get("addressLocality"), country_name(address.get("addressCountry"))]
        if name := ", ".join(part for part in parts if part):
            names.append(name)
    if posting.get("jobLocationType") == "TELECOMMUTE":  # schema.org's word for remote
        names.append("Remote")
    return " / ".join(names) or None


def _salary(base_salary: dict | None) -> str | None:
    """schema.org MonetaryAmount -> text the cleaner reads, e.g. "NPR 50000 - 70000 per month"."""
    if not base_salary:
        return None
    value = base_salary.get("value") or {}
    low, high = value.get("minValue"), value.get("maxValue")
    amount = f"{low} - {high}" if low and high else str(value.get("value") or low or high or "")
    if not amount:
        return None
    period = f" per {value['unitText'].lower()}" if value.get("unitText") else ""
    return f"{base_salary.get('currency', '')} {amount}{period}".strip()
