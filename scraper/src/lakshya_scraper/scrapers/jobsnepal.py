"""JobsNepal (www.jobsnepal.com): a job portal with server-rendered pages.

Listing: /jobs, 12 cards per page, the next page linked with rel="next".
Job page: schema.org microdata (itemprop="title", "experienceRequirements", ...), so the
scraper reads labelled structured fields instead of depending on the page layout.
"""

import re
from urllib.parse import urljoin

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.html import block_text, country_name, parse_html, text

BASE_URL = "https://www.jobsnepal.com"
_JOB_ID = re.compile(r"-(\d+)$")  # .../adminfinance-coordinator-144747 -> 144747


class JobsNepalScraper(Scraper):
    slug = "jobsnepal"

    def first_listing_url(self) -> str:
        return f"{BASE_URL}/jobs"

    def parse_listing(self, html: str, url: str) -> ListingPage:
        soup = parse_html(html)
        items = []
        for card in soup.select("div.card-body"):
            link = card.select_one("h2.job-title a[href]")
            match = _JOB_ID.search(link["href"]) if link else None
            if match is None:
                continue
            location_icon = card.select_one("i.icon-location4")
            items.append(
                ListingItem(
                    external_id=match.group(1),
                    url=urljoin(url, link["href"]),
                    title=text(link),
                    location=text(location_icon.find_next_sibling("div"))
                    if location_icon
                    else None,
                )
            )
        next_link = soup.select_one("a[rel=next][href]")
        return ListingPage(items, urljoin(url, next_link["href"]) if next_link else None)

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        soup = parse_html(html)
        job = soup.select_one('[itemtype*="schema.org/JobPosting"]') or soup

        def prop(name: str) -> str | None:
            element = job.select_one(f'[itemprop="{name}"]')
            if element is None:
                return None
            return element.get("content") or text(element)  # <meta content="..."> or visible text

        location = ", ".join(
            part for part in (prop("addressLocality"), country_name(prop("addressCountry"))) if part
        )
        return RawJob(
            source_slug=self.slug,
            external_id=item.external_id,
            url=item.url,
            title=prop("title"),
            company=text(job.select_one('[itemprop="hiringOrganization"] [itemprop="name"]')),
            location=location or None,
            salary=prop("baseSalary"),
            experience=prop("experienceRequirements"),
            deadline=text(job.select_one("span.apply-deadline")) or prop("validThrough"),
            posted=text(job.select_one("span.job-posted-on")) or prop("datePosted"),
            description=block_text(job.select_one('#div-job-details [itemprop="description"]')),
        )
