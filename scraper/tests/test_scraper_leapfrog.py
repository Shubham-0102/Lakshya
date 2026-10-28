"""Leapfrog careers scraper on trimmed copies of real pages (tests/fixtures/leapfrog)."""

import json
from pathlib import Path

import pytest

from lakshya_scraper.cleaning import clean
from lakshya_scraper.pipeline import worth_opening
from lakshya_scraper.scrapers import ListingItem
from lakshya_scraper.scrapers.leapfrog import LISTING_URL, LeapfrogScraper

FIXTURES = Path(__file__).parent / "fixtures" / "leapfrog"
JOB = ListingItem(
    "senior-full-stack-developer-3",
    "https://career.lftechnology.com/o/senior-full-stack-developer-3",
)

scraper = LeapfrogScraper()


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def job_page_with(**posting_changes) -> str:
    """The job fixture with some JSON-LD fields replaced."""
    html = read("job.html")
    start = html.index("{")
    end = html.index("</script>")
    posting = json.loads(html[start:end]) | posting_changes
    return html[:start] + json.dumps(posting) + html[end:]


def test_raw_html_has_no_openings_until_javascript_runs():
    """Why this source needs Playwright and listing_wait_for."""
    page = scraper.parse_listing(read("listing_before_javascript.html"), LISTING_URL)

    assert page.items == []


def test_listing_after_javascript_has_every_opening():
    page = scraper.parse_listing(read("listing.html"), LISTING_URL)

    assert len(page.items) == 9
    assert page.items[0] == ListingItem(
        "senior-security-engineer-1",
        "https://career.lftechnology.com/o/senior-security-engineer-1",
        "Senior Security Engineer",
        "Kathmandu, Nepal",
    )
    assert page.next_url is None


def test_talent_pool_and_pune_jobs_are_never_opened():
    page = scraper.parse_listing(read("listing.html"), LISTING_URL)

    opened = [item for item in page.items if worth_opening(item)]

    assert len(opened) == 5  # 9 openings - 3 in Pune - "Join our Talent Pool"
    assert all(item.location == "Kathmandu, Nepal" for item in opened)
    assert "Join our Talent Pool" not in {item.title for item in opened}


def test_job_page_is_read_from_json_ld():
    raw = scraper.parse_detail(read("job.html"), JOB)

    assert raw.title == "Senior Full-Stack Developer"
    assert raw.company == "Leapfrog Technology"
    assert raw.location == "Kathmandu, Nepal"
    assert raw.posted == "2025-12-10"
    assert raw.deadline is None  # validThrough is empty for this posting
    assert raw.salary is None
    assert raw.description.startswith("About Leapfrog\nLeapfrog is on a mission")


def test_job_page_cleans_into_a_complete_job():
    job = clean(scraper.parse_detail(read("job.html"), JOB))

    assert (job.title, job.company_normalized_name, job.location, job.is_remote) == (
        "Senior Full-Stack Developer",
        "leapfrog technology",
        "Kathmandu",
        False,
    )


def test_remote_job_location_and_structured_salary():
    html = job_page_with(
        jobLocationType="TELECOMMUTE",
        baseSalary={
            "@type": "MonetaryAmount",
            "currency": "NPR",
            "value": {
                "@type": "QuantitativeValue",
                "minValue": 150000,
                "maxValue": 200000,
                "unitText": "MONTH",
            },
        },
        validThrough="2026-11-30T23:59:59+05:45",
    )

    raw = scraper.parse_detail(html, JOB)
    job = clean(raw)

    assert raw.location == "Kathmandu, Nepal / Remote"
    assert raw.salary == "NPR 150000 - 200000 per month"
    assert (job.is_remote, job.salary_min, job.salary_max) == (True, 150_000, 200_000)
    assert str(job.deadline) == "2026-11-30"


def test_page_without_json_ld_is_an_error():
    with pytest.raises(ValueError, match="no JobPosting JSON-LD"):
        scraper.parse_detail("<html><body>Something else</body></html>", JOB)


def test_experience_comes_from_the_description():
    html = job_page_with(description="<p>Role</p><ul><li>5+ years of experience in React</li></ul>")

    assert scraper.parse_detail(html, JOB).experience == "5+ years of experience in React"
