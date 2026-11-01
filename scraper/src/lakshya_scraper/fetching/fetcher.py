"""PoliteFetcher: the only way the scraper fetches a page.

For every request: check robots.txt, wait for our turn (throttle), then load the page in
a real browser with our honest user agent. Images, fonts and media are not downloaded,
so each page view costs the site far fewer requests.
"""

import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Route
from playwright.sync_api import Error as PlaywrightError
from redis import Redis

from lakshya_scraper.fetching.robots import ALLOW_ALL, RobotsRules, disallow_all, parse_robots
from lakshya_scraper.fetching.throttle import wait_for_turn

logger = logging.getLogger(__name__)

_SKIPPED_RESOURCES = {"image", "media", "font"}


class FetchError(Exception):
    """A page couldn't be loaded (after retries, where retrying makes sense)."""


class RobotsDisallowed(FetchError):
    """robots.txt doesn't allow this URL; it was never requested."""


class StopRun(Exception):
    """Stop scraping this source for now."""


class PageLimitReached(StopRun):
    """The run used its request budget (SCRAPER_MAX_REQUESTS)."""


class SiteAskedToStop(StopRun):
    """The site answered 403 or 429: back off instead of pushing on."""


class PoliteFetcher:
    def __init__(
        self,
        *,
        browser: Browser,
        redis: Redis,
        throttle_key: str,
        min_delay: float,
        user_agent: str,
        max_requests: int,
        retries: int = 2,
        retry_wait: float = 10.0,
        timeout_ms: int = 30_000,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._redis = redis
        self._throttle_key = throttle_key  # one budget per source, even across several hosts
        self._min_delay = min_delay
        self._user_agent = user_agent
        self._max_requests = max_requests
        self._retries = retries
        self._retry_wait = retry_wait
        self._timeout_ms = timeout_ms
        self._sleep = sleep
        self._robots: dict[str, RobotsRules] = {}  # per host, read once per run
        self.requests_made = 0

        self._context = browser.new_context(user_agent=user_agent)
        self._context.route("**/*", self._skip_heavy_resources)
        self._page = self._context.new_page()

    def __enter__(self) -> "PoliteFetcher":
        return self

    def __exit__(self, *exc_info) -> None:
        self._context.close()

    def fetch(self, url: str, wait_for: str | None = None, settle_ms: int = 0) -> str:
        """Return the page's HTML after JavaScript ran. `wait_for`: a CSS selector that must
        appear first (for pages that build their content with JavaScript). `settle_ms`: time
        to let scripts run when we don't know yet what to wait for (a page being learned)."""

        def open_page() -> int | None:
            response = self._page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            return response.status if response else None

        self._request(url, open_page)
        if settle_ms:
            self._page.wait_for_timeout(settle_ms)
        return self._content(url, wait_for)

    def fetch_text(self, url: str) -> str:
        """Return a response body as it is, for feeds and APIs: nothing to render, so no page."""
        responses = []

        def get() -> int:
            responses.append(self._context.request.get(url, timeout=self._timeout_ms))
            return responses[-1].status

        self._request(url, get)
        return responses[-1].text()

    def _request(self, url: str, send: Callable[[], int | None]) -> None:
        """The rules for every request: robots.txt, the throttle, retries, and stopping when
        the site says so. Returns once `send` got a good answer."""
        robots = self._robots_for(url)
        if not robots.allows(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        delay = max(self._min_delay, robots.crawl_delay or 0)

        for attempt in range(self._retries + 1):
            self._take_turn(delay)
            started = time.monotonic()
            try:
                status = send()
            except PlaywrightError as error:  # timeout, connection refused, DNS, ...
                logger.warning("fetch %s failed: %s", url, error.message.splitlines()[0])
                status = None
            else:
                elapsed_ms = round((time.monotonic() - started) * 1000)
                logger.info("fetched %s -> %s (%d ms)", url, status, elapsed_ms)

            if status in (403, 429):
                raise SiteAskedToStop(f"{urlsplit(url).netloc} answered {status}")
            if status is not None and status < 400:
                return
            if status is not None and status < 500:
                raise FetchError(
                    f"{url} answered {status}"
                )  # 404 and the like: retrying won't help
            if attempt < self._retries:
                self._sleep(self._retry_wait * 3**attempt)  # 10 s, then 30 s

        raise FetchError(f"{url} failed after {self._retries + 1} attempts")

    def _content(self, url: str, wait_for: str | None) -> str:
        if wait_for:
            try:
                self._page.wait_for_selector(wait_for, timeout=self._timeout_ms)
            except PlaywrightError as error:
                raise FetchError(f"{wait_for!r} never appeared on {url}") from error
        return self._page.content()

    def _robots_for(self, url: str) -> RobotsRules:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            self._robots[host] = self._fetch_robots(f"{host}/robots.txt")
        return self._robots[host]

    def _fetch_robots(self, robots_url: str) -> RobotsRules:
        """RFC 9309: a 4xx means there are no rules; a 5xx or no answer means assume
        everything is disallowed until robots.txt can be read."""
        self._take_turn(self._min_delay)
        try:
            response = self._context.request.get(robots_url, timeout=self._timeout_ms)
        except PlaywrightError as error:
            logger.warning("could not read %s (%s): treating as disallow-all", robots_url, error)
            return disallow_all()
        logger.info("fetched %s -> %s", robots_url, response.status)
        if response.ok:
            return parse_robots(response.text(), self._user_agent)
        if 400 <= response.status < 500:
            return ALLOW_ALL
        return disallow_all()

    def _take_turn(self, delay: float) -> None:
        if self.requests_made >= self._max_requests:
            raise PageLimitReached(f"request limit of {self._max_requests} reached")
        wait_for_turn(self._redis, self._throttle_key, delay, sleep=self._sleep)
        self.requests_made += 1

    @staticmethod
    def _skip_heavy_resources(route: Route) -> None:
        if route.request.resource_type in _SKIPPED_RESOURCES:
            route.abort()
        else:
            route.continue_()
