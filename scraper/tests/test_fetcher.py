"""PoliteFetcher against a small local website, with a real headless Chromium.

The local site records every request it receives, so the tests can check what was and
wasn't requested, with which user agent, and how far apart.
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from lakshya_scraper.fetching import (
    FetchError,
    PageLimitReached,
    PoliteFetcher,
    RobotsDisallowed,
    SiteAskedToStop,
)

UA = "Lakshya/0.1 (+https://github.com/Shubham-0102/Lakshya; test)"
ALLOW_EVERYTHING = "User-agent: *\nDisallow:\n"


class LocalSite:
    """path -> responses, served in order (the last one repeats). Unknown paths get 404."""

    def __init__(self):
        self.responses: dict[str, list[tuple[int, str]]] = {}
        self.requests: list[tuple[str, str, float]] = []  # (path, user agent, time)
        self.base_url = ""

    def add(self, path: str, *responses: tuple[int, str]) -> None:
        self.responses[path] = list(responses)

    def paths(self) -> list[str]:
        return [path for path, _, _ in self.requests]

    def times(self, path: str) -> list[float]:
        return [at for requested, _, at in self.requests if requested == path]


@pytest.fixture
def site():
    local_site = LocalSite()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            local_site.requests.append((self.path, self.headers["User-Agent"], time.monotonic()))
            queue = local_site.responses.get(self.path)
            status, body = (queue.pop(0) if len(queue) > 1 else queue[0]) if queue else (404, "")
            data = body.encode()
            self.send_response(status)
            kind = "text/plain" if self.path.endswith(".txt") else "text/html"
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # keep test output quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    local_site.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    # poll_interval: how often shutdown() is noticed (default 0.5 s per test)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield local_site
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except PlaywrightError as error:
            pytest.fail(
                f"Chromium isn't installed. Run `uv run playwright install chromium`.\n{error}"
            )
        yield chromium
        chromium.close()


@pytest.fixture
def make_fetcher(browser, redis_client):
    def make(**overrides) -> PoliteFetcher:
        options = {
            "browser": browser,
            "redis": redis_client,
            "throttle_key": f"test-{uuid4()}",
            "min_delay": 0.05,  # real runs use the source's crawl delay (at least 5 s)
            "user_agent": UA,
            "max_requests": 50,
            "retry_wait": 0.01,
            "timeout_ms": 5_000,
        } | overrides
        return PoliteFetcher(**options)

    return make


def test_reads_robots_first_and_sends_our_user_agent(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/jobs", (200, "<h1>Jobs</h1>"))

    with make_fetcher() as fetcher:
        html = fetcher.fetch(f"{site.base_url}/jobs")

    assert "<h1>Jobs</h1>" in html
    assert site.paths()[:2] == ["/robots.txt", "/jobs"]
    assert {user_agent for _, user_agent, _ in site.requests} == {UA}


def test_disallowed_page_is_never_requested(site, make_fetcher):
    site.add("/robots.txt", (200, "User-agent: *\nDisallow: /private\n"))
    site.add("/private/jobs", (200, "secret"))

    with make_fetcher() as fetcher, pytest.raises(RobotsDisallowed):
        fetcher.fetch(f"{site.base_url}/private/jobs")

    assert "/private/jobs" not in site.paths()


def test_robots_is_read_once_per_host(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/a", (200, "a"))
    site.add("/b", (200, "b"))

    with make_fetcher() as fetcher:
        fetcher.fetch(f"{site.base_url}/a")
        fetcher.fetch(f"{site.base_url}/b")

    assert site.paths().count("/robots.txt") == 1


def test_requests_are_spaced_by_the_delay(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/a", (200, "a"))
    site.add("/b", (200, "b"))

    with make_fetcher(min_delay=0.5) as fetcher:
        fetcher.fetch(f"{site.base_url}/a")
        fetcher.fetch(f"{site.base_url}/b")

    times = [at for _, _, at in site.requests]
    assert all(later - earlier >= 0.45 for earlier, later in zip(times, times[1:], strict=False))


def test_crawl_delay_in_robots_wins_when_longer(site, make_fetcher):
    site.add("/robots.txt", (200, "User-agent: *\nCrawl-delay: 1\nDisallow:\n"))
    site.add("/a", (200, "a"))
    site.add("/b", (200, "b"))

    with make_fetcher(min_delay=0.05) as fetcher:
        fetcher.fetch(f"{site.base_url}/a")
        fetcher.fetch(f"{site.base_url}/b")

    assert site.times("/b")[0] - site.times("/a")[0] >= 0.95


def test_server_error_is_retried(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/flaky", (500, "oops"), (200, "<p>ok</p>"))

    with make_fetcher() as fetcher:
        html = fetcher.fetch(f"{site.base_url}/flaky")

    assert "<p>ok</p>" in html
    assert site.paths().count("/flaky") == 2


def test_server_error_gives_up_after_the_retries(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/down", (503, "down"))

    with make_fetcher(retries=2) as fetcher, pytest.raises(FetchError, match="after 3 attempts"):
        fetcher.fetch(f"{site.base_url}/down")

    assert site.paths().count("/down") == 3


def test_not_found_is_not_retried(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))

    with make_fetcher() as fetcher, pytest.raises(FetchError, match="404"):
        fetcher.fetch(f"{site.base_url}/missing")

    assert site.paths().count("/missing") == 1


@pytest.mark.parametrize("status", [403, 429])
def test_site_asking_us_to_stop_ends_the_run(site, make_fetcher, status):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/busy", (status, "slow down"))

    with make_fetcher() as fetcher, pytest.raises(SiteAskedToStop, match=str(status)):
        fetcher.fetch(f"{site.base_url}/busy")

    assert site.paths().count("/busy") == 1  # no retry


def test_request_limit_stops_the_run(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/a", (200, "a"))
    site.add("/b", (200, "b"))

    with make_fetcher(max_requests=2) as fetcher:  # robots.txt + /a
        fetcher.fetch(f"{site.base_url}/a")
        with pytest.raises(PageLimitReached):
            fetcher.fetch(f"{site.base_url}/b")

    assert "/b" not in site.paths()


def test_missing_robots_means_everything_is_allowed(site, make_fetcher):
    site.add("/jobs", (200, "jobs"))  # /robots.txt answers 404

    with make_fetcher() as fetcher:
        assert "jobs" in fetcher.fetch(f"{site.base_url}/jobs")


def test_robots_server_error_means_nothing_is_allowed(site, make_fetcher):
    site.add("/robots.txt", (503, "unavailable"))
    site.add("/jobs", (200, "jobs"))

    with make_fetcher() as fetcher, pytest.raises(RobotsDisallowed):
        fetcher.fetch(f"{site.base_url}/jobs")

    assert "/jobs" not in site.paths()


def test_images_are_not_downloaded(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/jobs", (200, '<img src="/photo.png"><p>Jobs</p>'))
    site.add("/photo.png", (200, "not really a png"))

    with make_fetcher() as fetcher:
        fetcher.fetch(f"{site.base_url}/jobs")

    assert "/photo.png" not in site.paths()


def test_waits_for_content_built_by_javascript(site, make_fetcher):
    page = """
        <ul id="openings"></ul>
        <script>
          setTimeout(() => {
            document.getElementById("openings").innerHTML = '<li class="job">Engineer</li>';
          }, 300);
        </script>
    """
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/careers", (200, page))

    with make_fetcher() as fetcher:
        html = fetcher.fetch(f"{site.base_url}/careers", wait_for="li.job")

    assert '<li class="job">Engineer</li>' in html


def test_missing_expected_element_is_a_fetch_error(site, make_fetcher):
    site.add("/robots.txt", (200, ALLOW_EVERYTHING))
    site.add("/careers", (200, "<p>Layout changed</p>"))

    with (
        make_fetcher(timeout_ms=1_000) as fetcher,
        pytest.raises(FetchError, match="never appeared"),
    ):
        fetcher.fetch(f"{site.base_url}/careers", wait_for="li.job")
