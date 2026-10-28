"""F1Soft Careers (career.f1soft.com): jobs at F1Soft and its group companies
(eSewa, Fonepay, FoneNXT, eXtensoData, ...).

Listing: /jobs, 8 cards (div.features-job) per page, the next page linked with rel="next".
The site also links every job from a navigation menu, so only the cards are read.
Job page: a "Job Overview" box of bold labels ("Organization Name:", "Location:",
"Application Deadline:") and the description in div.job-content.
"""

import re
from urllib.parse import urljoin, urlsplit

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.html import block_text, labelled_value, parse_html, text

BASE_URL = "https://career.f1soft.com"
_EXPERIENCE_LINE = re.compile(r"(?=.*\bexperience\b)(?=.*\d)", re.IGNORECASE)


class F1SoftScraper(Scraper):
    slug = "f1soft"

    def first_listing_url(self) -> str:
        return f"{BASE_URL}/jobs"

    def parse_listing(self, html: str, url: str) -> ListingPage:
        soup = parse_html(html)
        items = []
        for card in soup.select("div.features-job"):
            link = card.select_one("h3 a[href]")
            if link is None:
                continue
            job_url = urljoin(url, link["href"])
            items.append(
                ListingItem(
                    # No numeric id on this site: the URL slug identifies the job
                    external_id=urlsplit(job_url).path.rstrip("/").rsplit("/", 1)[-1],
                    url=job_url,
                    title=text(link),
                    location=text(card.select_one(".location-div .small")),
                )
            )
        next_link = soup.select_one("a[rel=next][href]")
        return ListingPage(items, urljoin(url, next_link["href"]) if next_link else None)

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        soup = parse_html(html)
        content = soup.select_one("div.job-content")
        description = block_text(content)
        return RawJob(
            source_slug=self.slug,
            external_id=item.external_id,
            url=item.url,
            title=text(soup.select_one("h2.fs-4")) or item.title,
            company=labelled_value(soup, "Organization Name"),
            location=labelled_value(soup, "Location"),
            salary=labelled_value(soup, "Salary"),
            # The line of the qualifications that states the experience needed
            experience=_first_line(description, _EXPERIENCE_LINE),
            deadline=labelled_value(soup, "Application Deadline"),
            description=description,
        )


def _first_line(text_block: str | None, pattern: re.Pattern) -> str | None:
    return next((line for line in (text_block or "").splitlines() if pattern.search(line)), None)
