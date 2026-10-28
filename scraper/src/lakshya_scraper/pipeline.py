"""The scraping pipeline: listing -> new postings -> fetch -> parse -> clean -> save.

run_source(slug) is the entry point (used by the CLI and by Celery). scrape() is the
pipeline itself, with the scraper, fetcher and session passed in so tests can use fakes.
preview_source(slug) is the dry run: the same fetching and cleaning, nothing saved.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from playwright.sync_api import sync_playwright
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lakshya_backend.config import get_settings
from lakshya_backend.db.models import ComplianceStatus, HealthStatus, Source
from lakshya_backend.db.session import get_session
from lakshya_scraper.cleaning import clean
from lakshya_scraper.cleaning.locations import clean_location
from lakshya_scraper.cleaning.titles import is_job_posting
from lakshya_scraper.fetching import (
    FetchError,
    PageLimitReached,
    PoliteFetcher,
    RobotsDisallowed,
    SiteAskedToStop,
    StopRun,
)
from lakshya_scraper.job_format import CleanJob, RawJob
from lakshya_scraper.scrapers import ListingItem, Scraper, get_scraper
from lakshya_scraper.storage import known_external_ids, mark_seen, save_job

logger = logging.getLogger(__name__)

FAILING_AFTER = 3  # runs in a row with a problem before a source counts as failing

Outcome = Literal["new", "skipped", "failed"]


class SourceNotAllowed(Exception):
    """The source is not enabled and approved in sources.yaml."""


@dataclass
class RunResult:
    source: str
    listing_pages: int = 0
    found: int = 0  # postings on the listing
    seen_again: int = 0  # already stored: only last_seen_at was updated
    new: int = 0  # saved as new jobs
    skipped: int = 0  # tenders, on-site jobs outside Nepal, pages robots.txt disallows
    failed: int = 0  # job pages that couldn't be fetched, read or saved
    stopped_early: str | None = None  # request limit reached, or the site asked us to stop
    problem: str | None = None  # why the source is degraded; None means healthy


@dataclass
class Preview:
    """One job page from a dry run: what the scraper read and what cleaning made of it."""

    item: ListingItem
    raw: RawJob | None = None
    job: CleanJob | None = None  # None with no error: skipped by cleaning
    error: str | None = None


def run_source(slug: str, limit: int | None = None) -> RunResult:
    """Scrape one source and save new jobs. `limit`: open at most this many job pages."""
    scraper = get_scraper(slug)
    with get_session() as session:
        source = _load_allowed_source(session, slug)
        with open_fetcher(slug, source.crawl_delay_seconds) as fetcher:
            result = scrape(session, source, scraper, fetcher, limit=limit)
    logger.info("run finished: %s", result)
    return result


def preview_source(slug: str, limit: int = 3) -> Iterator[Preview]:
    """Dry run: fetch, parse and clean up to `limit` job pages, without saving anything."""
    scraper = get_scraper(slug)
    with get_session() as session:
        crawl_delay = _load_allowed_source(session, slug).crawl_delay_seconds

    with open_fetcher(slug, crawl_delay) as fetcher:
        items = collect_listing(scraper, fetcher, RunResult(slug), max_pages=1)
        for item in [item for item in items if worth_opening(item)][:limit]:
            preview = Preview(item)
            try:
                html = fetcher.fetch(item.url, wait_for=scraper.detail_wait_for)
                preview.raw = scraper.parse_detail(html, item)
                preview.job = clean(preview.raw)
            except StopRun:
                raise
            except Exception as error:
                preview.error = f"{type(error).__name__}: {error}"
            yield preview


@contextmanager
def open_fetcher(slug: str, crawl_delay: float) -> Iterator[PoliteFetcher]:
    """A PoliteFetcher with a headless Chromium, closed again afterwards."""
    settings = get_settings()
    with Redis.from_url(settings.redis_url) as redis, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            with PoliteFetcher(
                browser=browser,
                redis=redis,
                throttle_key=f"source:{slug}",
                min_delay=crawl_delay,  # at least 5 s (database constraint)
                user_agent=settings.scraper_user_agent,
                max_requests=settings.scraper_max_requests,
            ) as fetcher:
                yield fetcher
        finally:
            browser.close()


def _load_allowed_source(session: Session, slug: str) -> Source:
    source = session.scalars(select(Source).where(Source.slug == slug)).one()
    ensure_allowed(source)
    return source


def ensure_allowed(source: Source) -> None:
    if not source.enabled or source.compliance_status != ComplianceStatus.APPROVED:
        raise SourceNotAllowed(f"{source.slug} is not enabled and approved (see sources.yaml)")


def scrape(
    session: Session,
    source: Source,
    scraper: Scraper,
    fetcher: PoliteFetcher,
    limit: int | None = None,
) -> RunResult:
    ensure_allowed(source)  # checked again here for callers that skip run_source
    started = datetime.now(UTC)
    result = RunResult(source.slug)

    items = collect_listing(scraper, fetcher, result)

    # Postings we already have are not fetched again
    known = known_external_ids(session, source.id)
    seen_again = [item.external_id for item in items if item.external_id in known]
    result.seen_again = mark_seen(session, source.id, seen_again, started)
    session.commit()

    new_items = [item for item in items if item.external_id not in known]
    opened = 0
    for item in new_items:
        if result.stopped_early:
            break
        if not worth_opening(item):
            result.skipped += 1
            continue
        if limit is not None and opened >= limit:
            break
        opened += 1
        try:
            outcome = _process(session, source, scraper, fetcher, item)
        except PageLimitReached as stop:
            result.stopped_early = str(stop)
        except SiteAskedToStop as stop:
            result.stopped_early = result.problem = str(stop)
        else:
            if outcome == "new":
                result.new += 1
            elif outcome == "skipped":
                result.skipped += 1
            else:
                result.failed += 1

    attempted = result.new + result.failed
    if not result.problem and result.failed > attempted / 2:
        result.problem = f"{result.failed} of {attempted} job pages failed"

    _update_health(source, result, started)
    session.commit()
    return result


def collect_listing(
    scraper: Scraper, fetcher: PoliteFetcher, result: RunResult, max_pages: int | None = None
) -> list[ListingItem]:
    items: dict[str, ListingItem] = {}
    url: str | None = scraper.first_listing_url()
    visited: set[str] = set()
    try:
        # `visited` stops a loop if a "next" link ever points back to an earlier page
        while url and url not in visited:
            visited.add(url)
            page = scraper.parse_listing(fetcher.fetch(url, wait_for=scraper.listing_wait_for), url)
            result.listing_pages += 1
            for item in page.items:
                items.setdefault(item.external_id, item)
            if not page.items or result.listing_pages == max_pages:
                break
            url = page.next_url
    except PageLimitReached as stop:
        result.stopped_early = str(stop)
    except SiteAskedToStop as stop:
        result.stopped_early = result.problem = str(stop)
    except Exception as error:  # the listing couldn't be fetched or read
        logger.exception("%s: listing page %s failed", result.source, url)
        result.problem = f"listing page failed: {error}"

    result.found = len(items)
    if not items and not result.problem:
        # Zero jobs usually means the page layout changed: the signal for self-healing (Phase 2)
        result.problem = "no jobs found on the listing (the page layout may have changed)"
    return list(items.values())


def worth_opening(item: ListingItem) -> bool:
    """Skip tenders and on-site jobs outside Nepal using what the listing already shows."""
    if item.title and not is_job_posting(item.title):
        logger.info("skipping %s: not a job posting (%r)", item.url, item.title)
        return False
    if item.location:
        location = clean_location(item.location)
        if location.outside_nepal and not location.is_remote:
            logger.info("skipping %s: outside Nepal (%r)", item.url, item.location)
            return False
    return True


def _process(
    session: Session, source: Source, scraper: Scraper, fetcher: PoliteFetcher, item: ListingItem
) -> Outcome:
    """Fetch, read, clean and save one new posting. StopRun errors are left to the caller."""
    try:
        html = fetcher.fetch(item.url, wait_for=scraper.detail_wait_for)
    except RobotsDisallowed:
        logger.info("%s: robots.txt disallows %s", source.slug, item.url)
        return "skipped"
    except FetchError as error:
        logger.warning("%s: %s", source.slug, error)
        return "failed"

    try:
        raw = scraper.parse_detail(html, item)
        job = clean(raw)
    except Exception:  # a page layout the scraper doesn't understand
        logger.exception("%s: could not read job page %s", source.slug, item.url)
        return "failed"
    if job is None:
        return "skipped"

    try:
        save_job(session, source, raw, job)
        session.commit()  # each job is committed alone, so a later failure can't undo it
    except SQLAlchemyError:
        session.rollback()
        logger.exception("%s: could not save %s", source.slug, item.url)
        return "failed"
    return "new"


def _update_health(source: Source, result: RunResult, started: datetime) -> None:
    source.last_run_at = started
    if result.problem:
        source.failure_count += 1
        failing = source.failure_count >= FAILING_AFTER
        source.health_status = HealthStatus.FAILING if failing else HealthStatus.DEGRADED
        logger.warning("%s is %s: %s", source.slug, source.health_status, result.problem)
    else:
        source.failure_count = 0
        source.health_status = HealthStatus.HEALTHY
        source.last_success_at = started
