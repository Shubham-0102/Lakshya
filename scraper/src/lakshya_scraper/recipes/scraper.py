"""RecipeScraper: follows a recipe with plain code. No AI runs here.

It keeps the same contract as a hand-written scraper, so the pipeline treats both alike.
"""

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from lakshya_scraper.job_format import RawJob
from lakshya_scraper.recipes.format import Pick, Picks, Recipe
from lakshya_scraper.scrapers.base import ListingItem, ListingPage, Scraper
from lakshya_scraper.scrapers.html import (
    block_text,
    country_name,
    experience_line,
    html_to_text,
    json_ld_job_posting,
    labelled_value,
    parse_html,
    text,
)

_TRAILING_NUMBER = re.compile(r"-(\d+)$")  # .../adminfinance-coordinator-144747 -> 144747


class RecipeScraper(Scraper):
    def __init__(self, slug: str, listing_url: str, recipe: Recipe):
        self.slug = slug
        self.listing_url = listing_url
        self.recipe = recipe
        self.listing_wait_for = recipe.listing.wait_for
        self.detail_wait_for = recipe.job.wait_for

    def first_listing_url(self) -> str:
        return self.listing_url

    def parse_listing(self, html: str, url: str) -> ListingPage:
        rules = self.recipe.listing
        soup = parse_html(html)
        items = []
        for posting in soup.select(rules.item):
            link = posting.select_one(rules.link)
            if link is None or not link.get("href"):
                continue
            job_url = urljoin(url, link["href"])
            external_id = self._job_id(job_url)
            if external_id:
                items.append(
                    ListingItem(
                        external_id=external_id,
                        url=job_url,
                        title=_listing_text(posting, rules.title),
                        location=_listing_text(posting, rules.location),
                    )
                )
        next_link = soup.select_one(rules.next_page) if rules.next_page else None
        has_next = next_link is not None and next_link.get("href")
        return ListingPage(items, urljoin(url, next_link["href"]) if has_next else None)

    def _job_id(self, job_url: str) -> str | None:
        last_segment = urlsplit(job_url).path.rstrip("/").rsplit("/", 1)[-1]
        if self.recipe.listing.job_id == "last_path_segment":
            return last_segment or None
        match = _TRAILING_NUMBER.search(last_segment)
        return match.group(1) if match else None

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        rules = self.recipe.job
        soup = parse_html(html)
        posting = json_ld_job_posting(soup) or {}

        description = _first(rules.description, soup, posting, multiline=True)
        experience = _first(rules.experience, soup, posting)
        # A field can say only "Please check vacancy details": prefer a line that gives numbers
        if not experience or not re.search(r"\d", experience):
            experience = experience_line(description) or experience

        return RawJob(
            source_slug=self.slug,
            external_id=item.external_id,
            url=item.url,
            title=_first(rules.title, soup, posting) or item.title,
            company=_first(rules.company, soup, posting),
            location=_location(rules.location, rules.country, soup, posting),
            salary=_first(rules.salary, soup, posting),
            experience=experience,
            deadline=_first(rules.deadline, soup, posting),
            posted=_first(rules.posted, soup, posting),
            description=description,
        )


def _listing_text(posting, selector: str | None) -> str | None:
    return text(posting.select_one(selector)) if selector else None


def _location(place: Picks, country: Picks, soup: BeautifulSoup, posting: dict) -> str | None:
    parts = [_first(place, soup, posting), country_name(_first(country, soup, posting))]
    return ", ".join(part for part in parts if part) or None


def _first(picks: Picks, soup: BeautifulSoup, posting: dict, multiline: bool = False) -> str | None:
    for pick in picks:
        if value := _read(pick, soup, posting, multiline):
            return value
    return None


def _read(pick: Pick, soup: BeautifulSoup, posting: dict, multiline: bool) -> str | None:
    if pick.fixed:
        return pick.fixed
    if pick.label:
        return labelled_value(soup, pick.label)
    if pick.json_ld:
        value = _json_value(posting, pick.json_ld)
        return html_to_text(value) if value and multiline else value

    element = soup.select_one(pick.css)
    if element is None:
        return None
    if multiline:
        return block_text(element)
    return element.get("content") or text(element)  # <meta content="..."> or visible text


def _json_value(posting: dict, path: str) -> str | None:
    """Walk a dotted path. A list (several locations, say) means its first entry."""
    value = posting
    for key in path.split("."):
        if isinstance(value, list):
            value = value[0] if value else None
        value = value.get(key) if isinstance(value, dict) else None
    return str(value) if isinstance(value, str | int | float) and value != "" else None
