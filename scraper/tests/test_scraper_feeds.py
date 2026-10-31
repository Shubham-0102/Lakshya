"""The feed scrapers, on hand-written files in the shape of each feed (no network)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from lakshya_backend.db.models import SalaryPeriod
from lakshya_scraper.cleaning import clean
from lakshya_scraper.fetching.robots import parse_robots
from lakshya_scraper.pipeline import worth_opening
from lakshya_scraper.scrapers.arbeitnow import ArbeitnowScraper
from lakshya_scraper.scrapers.feed_fields import day_from_epoch, remote_location, salary_text
from lakshya_scraper.scrapers.himalayas import HimalayasScraper
from lakshya_scraper.scrapers.jobicy import JobicyScraper
from lakshya_scraper.scrapers.remoteok import RemoteOkScraper

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def listing(scraper, name: str, url: str | None = None):
    return scraper.parse_listing(fixture(name), url or scraper.first_listing_url())


def by_slug(page) -> dict:
    return {item.external_id: item for item in page.items}


# Himalayas


def test_himalayas_reads_a_whole_job_from_the_listing():
    item = listing(HimalayasScraper(), "himalayas/search.json").items[0]

    assert item.title == "Backend Engineer & Team Lead (Remote)"
    assert item.url == "https://himalayas.app/companies/example-labs/jobs/backend-engineer"
    raw = item.raw
    assert raw.company == "Example Labs"
    assert raw.location == "Remote"
    assert raw.salary == "USD 3000 - 6000 per month"
    assert raw.experience == "3+ years of experience with Python"
    assert raw.deadline == "2026-11-28"
    assert "You will build APIs." in raw.description
    assert "<p>" not in raw.description


def test_himalayas_apply_link_is_the_feed_link():
    """A condition of use: never a direct employer link."""
    raw = listing(HimalayasScraper(), "himalayas/search.json").items[0].raw

    assert str(raw.url) == "https://himalayas.app/companies/example-labs/jobs/backend-engineer"


def test_himalayas_cleans_to_a_remote_job_with_pay():
    job = clean(listing(HimalayasScraper(), "himalayas/search.json").items[0].raw)

    assert job.is_remote
    assert job.location is None
    assert (job.salary_min, job.salary_max, job.salary_currency) == (3000, 6000, "USD")
    assert job.salary_period == SalaryPeriod.MONTH
    assert job.experience_min_years == Decimal(3)


def test_himalayas_keeps_a_job_whose_country_list_includes_nepal():
    page = listing(HimalayasScraper(), "himalayas/search.json")

    assert page.items[1].raw.company == "Sample Works"
    assert page.items[1].raw.salary is None


def test_himalayas_uses_seniority_when_the_description_gives_no_years():
    raw = listing(HimalayasScraper(), "himalayas/search.json").items[1].raw

    assert raw.experience == "Entry-level"
    assert clean(raw).experience_min_years == 0


def test_himalayas_leaves_out_jobs_limited_to_other_countries_or_time_zones():
    page = listing(HimalayasScraper(), "himalayas/search.json")

    assert len(page.items) == 2  # of 4: one is US only, one works US hours only


def himalayas_searches() -> list[str]:
    scraper, urls = HimalayasScraper(), [HimalayasScraper().first_listing_url()]
    while next_url := scraper.parse_listing('{"jobs": []}', urls[-1]).next_url:
        urls.append(next_url)
    return urls


def test_himalayas_walks_through_every_search_once():
    urls = himalayas_searches()

    assert len(urls) == len(set(urls)) > 40
    assert all("country=Nepal" in url for url in urls)
    assert "seniority=Entry-level" in urls[0]
    assert any("q=machine%20learning" in url for url in urls)


def test_himalayas_never_asks_for_a_url_its_robots_txt_disallows():
    """Copied from the real file. Its docs page with page=2, but robots.txt forbids that."""
    robots = parse_robots(
        "User-Agent: *\nAllow: /\nDisallow: /apply\nDisallow: /jobs?page=\n"
        "Disallow: /jobs*&page=\nDisallow: /jobs/*?page=\n",
        "Lakshya/0.1",
    )

    assert not robots.allows("https://himalayas.app/jobs/api/search?country=Nepal&page=1")
    assert all(robots.allows(url) for url in himalayas_searches())
    assert not any("page=" in url or "offset=" in url for url in himalayas_searches())


def test_himalayas_runs_once_a_day_because_its_data_does():
    assert HimalayasScraper.min_hours_between_runs == 20


# Remote OK


def test_remoteok_skips_the_legal_notice():
    page = listing(RemoteOkScraper(), "remoteok/feed.json")

    assert sorted(by_slug(page)) == ["101", "102", "103"]
    assert page.next_url is None


def test_remoteok_reads_a_whole_job_and_decodes_html_entities():
    raw = by_slug(listing(RemoteOkScraper(), "remoteok/feed.json"))["101"].raw

    assert raw.title == "Sales & Support Engineer"
    assert raw.company == "Example & Sons"
    assert raw.location == "Remote"
    assert raw.salary == "USD 80000 - 100000 per year"
    assert raw.experience == "2+ years of experience in support."
    assert str(raw.url) == "https://remoteok.com/remote-jobs/sales-and-support-example-labs-101"


def test_remoteok_zero_salary_means_not_given():
    raw = by_slug(listing(RemoteOkScraper(), "remoteok/feed.json"))["102"].raw

    assert raw.salary is None


def test_remoteok_worldwide_job_is_kept():
    item = by_slug(listing(RemoteOkScraper(), "remoteok/feed.json"))["102"]

    assert worth_opening(item)
    assert clean(item.raw).is_remote


def test_remoteok_job_limited_to_a_place_is_dropped_before_saving():
    item = by_slug(listing(RemoteOkScraper(), "remoteok/feed.json"))["103"]

    assert item.location == "Remote - Boston"
    assert not worth_opening(item)
    assert clean(item.raw) is None


# Arbeitnow


def test_arbeitnow_keeps_only_remote_jobs():
    page = listing(ArbeitnowScraper(), "arbeitnow/page1.json")

    assert sorted(by_slug(page)) == [
        "designer-sample-works-2",
        "platform-engineer-example-labs-1",
        "sales-sample-works-3",
    ]


def test_arbeitnow_reads_a_whole_job():
    raw = by_slug(listing(ArbeitnowScraper(), "arbeitnow/page1.json"))[
        "platform-engineer-example-labs-1"
    ].raw

    assert raw.company == "Example Labs GmbH"
    assert raw.location == "Remote"
    assert raw.experience == "4+ years of experience with Kubernetes."
    assert raw.posted == "2026-10-31"


def test_arbeitnow_remote_job_tied_to_a_city_is_dropped():
    item = by_slug(listing(ArbeitnowScraper(), "arbeitnow/page1.json"))["sales-sample-works-3"]

    assert not worth_opening(item)


def test_arbeitnow_remote_job_wording_is_kept():
    item = by_slug(listing(ArbeitnowScraper(), "arbeitnow/page1.json"))["designer-sample-works-2"]

    assert item.location == "Remote job"  # real wording
    assert worth_opening(item)


def test_arbeitnow_follows_the_next_link():
    page = listing(ArbeitnowScraper(), "arbeitnow/page1.json")

    assert page.next_url == "https://www.arbeitnow.com/api/job-board-api?page=2"


def test_arbeitnow_stops_after_the_page_limit():
    html = fixture("arbeitnow/page1.json").replace('"current_page": 1', '"current_page": 5')

    assert ArbeitnowScraper().parse_listing(html, "unused").next_url is None


# Jobicy


def test_jobicy_reads_a_whole_job():
    raw = by_slug(listing(JobicyScraper(), "jobicy/jobs.json"))["501"].raw

    assert raw.title == "Data Engineer & Analyst"
    assert raw.company == "Example Labs"
    assert raw.location == "Remote - Anywhere"
    assert raw.salary == "USD 60000 - 90000 per year"
    assert raw.experience == "Senior"
    assert str(raw.url) == "https://jobicy.com/jobs/501-data-engineer"


def test_jobicy_prefers_years_in_the_description_over_its_level():
    raw = by_slug(listing(JobicyScraper(), "jobicy/jobs.json"))["502"].raw

    assert raw.experience == "2 years of experience in support."


def test_jobicy_keeps_jobs_open_to_nepal_and_drops_the_rest():
    items = by_slug(listing(JobicyScraper(), "jobicy/jobs.json"))

    assert worth_opening(items["501"])  # Anywhere
    assert worth_opening(items["502"])  # APAC
    assert not worth_opening(items["503"])  # USA


def test_jobicy_cursor_is_url_encoded():
    page = listing(JobicyScraper(), "jobicy/jobs.json")

    assert page.next_url == "https://jobicy.com/api/jobs?count=100&cursor=abc%2B%2F%3Ddef"


def test_jobicy_last_page_has_no_next_url():
    html = fixture("jobicy/jobs.json").replace('"abc+/=def"', "null")

    assert JobicyScraper().parse_listing(html, "unused").next_url is None


# Shared helpers


@pytest.mark.parametrize(
    ("place", "expected"),
    [
        (None, "Remote"),
        ("", "Remote"),
        ("  ", "Remote"),
        ("Remote", "Remote"),
        ("Remote - US", "Remote - US"),
        ("Boston", "Remote - Boston"),
    ],
)
def test_remote_location(place, expected):
    assert remote_location(place) == expected


@pytest.mark.parametrize(
    ("low", "high", "currency", "period", "expected"),
    [
        (3000, 6000, "USD", "monthly", "USD 3000 - 6000 per month"),
        (55000, 70000, "USD", "annual", "USD 55000 - 70000 per year"),
        (20, 30, "USD", "hourly", "USD 20 - 30 per hour"),
        (100, 100, "USD", "hourly", "USD 100 per hour"),  # real: both ends equal
        (5000, None, "EUR", "monthly", "EUR 5000 per month"),
        (5000, 6000, "EUR", None, "EUR 5000 - 6000"),
        (None, None, None, "annual", None),  # real: period without pay
        (0, 0, "USD", "year", None),  # real: Remote OK's "not given"
    ],
)
def test_salary_text(low, high, currency, period, expected):
    assert salary_text(low, high, currency, period) == expected


def test_day_from_epoch():
    assert day_from_epoch(1793455253) == date(2026, 10, 31).isoformat()
    assert day_from_epoch(None) is None
