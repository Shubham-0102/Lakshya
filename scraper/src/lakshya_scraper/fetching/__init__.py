"""Polite fetching: robots.txt, throttling and the browser. Every request to a site goes
through PoliteFetcher, so the scraping rules can't be skipped by accident."""

from lakshya_scraper.fetching.fetcher import (
    FetchError,
    PageLimitReached,
    PoliteFetcher,
    RobotsDisallowed,
    SiteAskedToStop,
    StopRun,
)

__all__ = [
    "FetchError",
    "PageLimitReached",
    "PoliteFetcher",
    "RobotsDisallowed",
    "SiteAskedToStop",
    "StopRun",
]
