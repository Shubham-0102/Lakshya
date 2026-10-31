"""The contract every site scraper follows.

A scraper only knows its own site's pages: where the listing starts, how to read a listing
page and how to read a job page. Fetching (robots.txt, throttling, retries), cleaning and
saving are done by the pipeline, the same way for every site.

A feed (an official API or RSS feed) is simpler: its listing already holds whole jobs, so
there are no job pages to open and no HTML to read.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from lakshya_scraper.job_format import RawJob

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ListingItem:
    """One posting found on a listing page."""

    external_id: str
    url: str
    # If the listing shows these, the pipeline can skip tenders and jobs limited to outside
    # Nepal without opening their job pages (fewer requests to the site)
    title: str | None = None
    location: str | None = None
    raw: RawJob | None = None  # the whole job, if the listing gives it: no job page to open


@dataclass(frozen=True)
class ListingPage:
    items: list[ListingItem]
    next_url: str | None = None  # None on the last page


class Scraper(ABC):
    slug: str  # matches sources.slug
    is_feed = False  # True: the listing is fetched as plain text, without a browser page
    # CSS selectors to wait for on pages that build their content with JavaScript
    listing_wait_for: str | None = None
    detail_wait_for: str | None = None

    @abstractmethod
    def first_listing_url(self) -> str: ...

    @abstractmethod
    def parse_listing(self, html: str, url: str) -> ListingPage: ...

    @abstractmethod
    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        """Copy the page's text into a RawJob without interpreting it (cleaning does that)."""


class FeedScraper(Scraper):
    """A source with an official feed. Every entry becomes a RawJob straight from the listing."""

    is_feed = True

    @abstractmethod
    def parse_entry(self, entry: dict) -> RawJob | None:
        """One feed entry -> RawJob, or None for a job people in Nepal can't take."""

    def items(self, entries: list[dict]) -> list[ListingItem]:
        items = []
        for entry in entries:
            try:
                raw = self.parse_entry(entry)
            except (KeyError, TypeError, ValueError):  # one odd entry mustn't lose the whole page
                logger.warning("%s: skipping an unreadable feed entry", self.slug, exc_info=True)
                continue
            if raw:
                items.append(
                    ListingItem(raw.external_id, str(raw.url), raw.title, raw.location, raw)
                )
        return items

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        raise NotImplementedError("feeds have no job pages: the pipeline uses item.raw")
