"""The pipeline with a fake site: a fake scraper reads JSON "pages" served by a fake fetcher.

The real database (lakshya_test) is used, so saving, duplicates and health are real.
"""

import json

import pytest
from sqlalchemy import func, select

from lakshya_backend.db.models import (
    Company,
    ComplianceStatus,
    HealthStatus,
    Job,
    JobSource,
    Source,
    SourceType,
)
from lakshya_scraper.fetching import FetchError, PageLimitReached, RobotsDisallowed, SiteAskedToStop
from lakshya_scraper.job_format import RawJob
from lakshya_scraper.pipeline import SourceNotAllowed, scrape
from lakshya_scraper.scrapers import ListingItem, ListingPage, Scraper

BASE = "https://jobs.example.com"
FIRST_PAGE = f"{BASE}/jobs?page=1"


class FakeScraper(Scraper):
    """Listing pages and job pages are JSON, so the tests can focus on the pipeline."""

    slug = "example"

    def first_listing_url(self) -> str:
        return FIRST_PAGE

    def parse_listing(self, html: str, url: str) -> ListingPage:
        data = json.loads(html)
        items = [
            ListingItem(
                job["id"], f"{BASE}/jobs/{job['id']}", job.get("title"), job.get("location")
            )
            for job in data["items"]
        ]
        return ListingPage(items, data.get("next"))

    def parse_detail(self, html: str, item: ListingItem) -> RawJob:
        return RawJob(
            source_slug=self.slug, external_id=item.external_id, url=item.url, **json.loads(html)
        )


class FakeFetcher:
    """url -> page text, or an exception to raise. Records every URL it was asked for."""

    def __init__(self, pages: dict[str, str | Exception]):
        self.pages = pages
        self.fetched: list[str] = []

    def fetch(self, url: str, wait_for: str | None = None) -> str:
        self.fetched.append(url)
        page = self.pages.get(url, FetchError(f"{url} answered 404"))
        if isinstance(page, Exception):
            raise page
        return page


def listing(*jobs: dict, next_url: str | None = None) -> str:
    return json.dumps({"items": list(jobs), "next": next_url})


def job_page(title="Backend Engineer", company="Acme Pvt. Ltd.", **fields) -> str:
    return json.dumps({"title": title, "company": company, "location": "Kathmandu"} | fields)


def site_with_jobs(*ids: str) -> dict[str, str | Exception]:
    pages: dict[str, str | Exception] = {FIRST_PAGE: listing(*({"id": i} for i in ids))}
    for i in ids:
        pages[f"{BASE}/jobs/{i}"] = job_page(title=f"Engineer {i}")
    return pages


@pytest.fixture
def source(db_session):
    example = Source(
        slug="example",
        name="Example Jobs",
        base_url=BASE,
        type=SourceType.PORTAL,
        compliance_status=ComplianceStatus.APPROVED,
        enabled=True,
    )
    db_session.add(example)
    db_session.flush()
    return example


def run(db_session, source, pages):
    fetcher = FakeFetcher(pages)
    result = scrape(db_session, source, FakeScraper(), fetcher)
    db_session.refresh(source)
    return result, fetcher


def count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


# --- Saving and duplicates ------------------------------------------------------------


def test_first_run_saves_new_jobs(db_session, source):
    result, _ = run(db_session, source, site_with_jobs("1", "2"))

    assert (result.found, result.new, result.failed) == (2, 2, 0)
    assert count(db_session, Job) == 2
    assert count(db_session, Company) == 1  # both jobs are at "Acme Pvt. Ltd."
    assert source.health_status == HealthStatus.HEALTHY


def test_second_run_only_reads_the_listing_and_marks_jobs_seen(db_session, source):
    pages = site_with_jobs("1", "2")
    run(db_session, source, pages)
    first_seen = {s.external_id: s.last_seen_at for s in db_session.scalars(select(JobSource))}

    result, fetcher = run(db_session, source, pages)

    assert (result.new, result.seen_again) == (0, 2)
    assert fetcher.fetched == [FIRST_PAGE]  # no job page was requested again
    assert count(db_session, Job) == 2
    db_session.expire_all()
    for link in db_session.scalars(select(JobSource)):
        assert link.last_seen_at > first_seen[link.external_id]


def test_link_back_and_raw_record_are_stored(db_session, source):
    run(db_session, source, site_with_jobs("42"))

    link = db_session.scalars(select(JobSource)).one()
    assert link.url == f"{BASE}/jobs/42"
    assert link.raw["title"] == "Engineer 42"
    assert link.raw["company"] == "Acme Pvt. Ltd."
    assert link.job.company.normalized_name == "acme"


def test_pagination_follows_next_links_and_never_loops(db_session, source):
    second_page = f"{BASE}/jobs?page=2"
    pages = site_with_jobs("1") | site_with_jobs("2")
    pages[FIRST_PAGE] = listing({"id": "1"}, next_url=second_page)
    pages[second_page] = listing({"id": "2"}, next_url=FIRST_PAGE)  # points back: a loop

    result, _ = run(db_session, source, pages)

    assert (result.listing_pages, result.new) == (2, 2)


# --- Skipping without opening the job page --------------------------------------------


def test_tender_on_the_listing_is_skipped_without_opening_it(db_session, source):
    pages = site_with_jobs("1")
    pages[FIRST_PAGE] = listing({"id": "1"}, {"id": "2", "title": "Call for Bid: Office Supplies"})

    result, fetcher = run(db_session, source, pages)

    assert (result.new, result.skipped) == (1, 1)
    assert f"{BASE}/jobs/2" not in fetcher.fetched


def test_onsite_job_outside_nepal_is_skipped_without_opening_it(db_session, source):
    pages = site_with_jobs("1")
    pages[FIRST_PAGE] = listing({"id": "1"}, {"id": "2", "location": "Pune, India"})

    result, fetcher = run(db_session, source, pages)

    assert (result.new, result.skipped) == (1, 1)
    assert f"{BASE}/jobs/2" not in fetcher.fetched


def test_job_page_disallowed_by_robots_is_skipped(db_session, source):
    pages = site_with_jobs("1", "2")
    pages[f"{BASE}/jobs/2"] = RobotsDisallowed("robots.txt disallows it")

    result, _ = run(db_session, source, pages)

    assert (result.new, result.skipped, result.failed) == (1, 1, 0)


# --- Failures and source health -------------------------------------------------------


def test_one_broken_job_page_does_not_stop_the_run(db_session, source):
    pages = site_with_jobs("1", "2", "3")
    del pages[f"{BASE}/jobs/2"]  # 404

    result, _ = run(db_session, source, pages)

    assert (result.new, result.failed) == (2, 1)
    assert source.health_status == HealthStatus.HEALTHY


def test_most_job_pages_failing_marks_the_source_degraded(db_session, source):
    pages = site_with_jobs("1", "2", "3")
    del pages[f"{BASE}/jobs/2"]  # 404
    pages[f"{BASE}/jobs/3"] = "<html>not what the scraper expects</html>"  # layout changed

    result, _ = run(db_session, source, pages)

    assert (result.new, result.failed) == (1, 2)
    assert result.problem == "2 of 3 job pages failed"
    assert source.health_status == HealthStatus.DEGRADED


def test_empty_listing_marks_the_source_degraded_then_failing(db_session, source):
    pages = {FIRST_PAGE: listing()}

    statuses = []
    for _ in range(3):
        run(db_session, source, pages)
        statuses.append(source.health_status)

    assert statuses == [HealthStatus.DEGRADED, HealthStatus.DEGRADED, HealthStatus.FAILING]
    assert source.failure_count == 3


def test_a_good_run_resets_the_failure_count(db_session, source):
    source.failure_count, source.health_status = 2, HealthStatus.DEGRADED

    run(db_session, source, site_with_jobs("1"))

    assert (source.failure_count, source.health_status) == (0, HealthStatus.HEALTHY)
    assert source.last_success_at is not None


def test_listing_that_cannot_be_fetched_is_a_problem(db_session, source):
    result, fetcher = run(db_session, source, {FIRST_PAGE: FetchError("answered 500")})

    assert result.problem.startswith("listing page failed")
    assert fetcher.fetched == [FIRST_PAGE]
    assert source.health_status == HealthStatus.DEGRADED


def test_site_asking_us_to_stop_ends_the_run(db_session, source):
    pages = site_with_jobs("1", "2", "3")
    pages[f"{BASE}/jobs/2"] = SiteAskedToStop("jobs.example.com answered 429")

    result, fetcher = run(db_session, source, pages)

    assert result.new == 1
    assert result.stopped_early == result.problem == "jobs.example.com answered 429"
    assert f"{BASE}/jobs/3" not in fetcher.fetched
    assert source.health_status == HealthStatus.DEGRADED


def test_request_limit_ends_the_run_but_is_not_a_problem(db_session, source):
    pages = site_with_jobs("1", "2")
    pages[f"{BASE}/jobs/2"] = PageLimitReached("request limit of 300 reached")

    result, _ = run(db_session, source, pages)

    assert result.new == 1
    assert result.stopped_early == "request limit of 300 reached"
    assert result.problem is None
    assert source.health_status == HealthStatus.HEALTHY


def test_source_that_is_not_enabled_is_refused(db_session, source):
    source.enabled = False
    fetcher = FakeFetcher(site_with_jobs("1"))

    with pytest.raises(SourceNotAllowed):
        scrape(db_session, source, FakeScraper(), fetcher)

    assert fetcher.fetched == []
