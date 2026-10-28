"""F1Soft Careers scraper on trimmed copies of real pages (tests/fixtures/f1soft)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from lakshya_scraper.cleaning import clean
from lakshya_scraper.scrapers import ListingItem
from lakshya_scraper.scrapers.f1soft import F1SoftScraper

FIXTURES = Path(__file__).parent / "fixtures" / "f1soft"
LISTING_URL = "https://career.f1soft.com/jobs"
JOB = ListingItem(
    "business-analyst-fonenxt", "https://career.f1soft.com/jobs/business-analyst-fonenxt"
)

scraper = F1SoftScraper()


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_listing_reads_the_job_cards_and_the_next_page():
    page = scraper.parse_listing(read("listing.html"), LISTING_URL)

    assert [i.external_id for i in page.items] == [
        "backend-engineer-galli",
        "sales-officer-f1",
        "research-and-strategic-planning-officer",
    ]
    assert page.items[0].title == "Backend Engineer"
    assert page.items[0].location == "Pulchowk, Lalitpur District, Nepal"
    assert page.items[0].url == "https://career.f1soft.com/jobs/backend-engineer-galli"
    assert page.next_url == "https://career.f1soft.com/jobs?page=2"


def test_job_page_is_read_from_its_labelled_fields():
    raw = scraper.parse_detail(read("job.html"), JOB)

    assert raw.title == "Business Analyst"
    assert raw.company == "FoneNXT"  # the group company, not "F1Soft"
    assert raw.location == "F1Soft Tower, Pulchowk, Lalitpur District, Nepal"
    assert raw.deadline == "2026-10-30"
    assert raw.experience == "2-3 years of prior work experience in BA roles."
    assert raw.salary is None
    assert raw.description.startswith("A dedicated Business Analyst will institutionalize")
    assert "Qualification and Experience" in raw.description


def test_job_page_cleans_into_a_complete_job():
    job = clean(scraper.parse_detail(read("job.html"), JOB))

    assert (job.title, job.company_normalized_name, job.location) == (
        "Business Analyst",
        "fonenxt",
        "Lalitpur",
    )
    assert job.deadline == date(2026, 10, 30)
    assert (job.experience_min_years, job.experience_max_years) == (Decimal("2"), Decimal("3"))
