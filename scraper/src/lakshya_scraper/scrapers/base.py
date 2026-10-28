"""The contract every site scraper follows.

A scraper only knows its own site's pages: where the listing starts, how to read a listing
page and how to read a job page. Fetching (robots.txt, throttling, retries), cleaning and
saving are done by the pipeline, the same way for every site.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from lakshya_scraper.job_format import RawJob


@dataclass(frozen=True)
class ListingItem:
    """One posting found on a listing page."""

    external_id: str
    url: str
    # If the listing shows these, the pipeline can skip tenders and on-site jobs outside
    # Nepal without opening their job pages (fewer requests to the site)
    title: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class ListingPage:
    items: list[ListingItem]
    next_url: str | None = None  # None on the last page


class Scraper(ABC):
    slug: str  # matches sources.slug
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
