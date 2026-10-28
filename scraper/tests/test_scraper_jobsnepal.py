"""JobsNepal scraper on trimmed copies of real pages (tests/fixtures/jobsnepal)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from lakshya_scraper.cleaning import clean
from lakshya_scraper.pipeline import worth_opening
from lakshya_scraper.scrapers import ListingItem
from lakshya_scraper.scrapers.jobsnepal import JobsNepalScraper

FIXTURES = Path(__file__).parent / "fixtures" / "jobsnepal"
LISTING_URL = "https://www.jobsnepal.com/jobs"
JOB = ListingItem("144747", "https://www.jobsnepal.com/adminfinance-coordinator-144747")

scraper = JobsNepalScraper()


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_listing_reads_every_card_and_the_next_page():
    page = scraper.parse_listing(read("listing.html"), LISTING_URL)

    assert [(i.external_id, i.location) for i in page.items] == [
        ("144748", "Kathmandu"),
        ("144747", "Kathmandu"),
        ("144746", "Dhading"),
        ("144742", "Jajarkot"),
    ]
    assert page.items[1].title == "Admin/Finance Coordinator"
    assert page.items[1].url == JOB.url
    assert page.next_url == "https://www.jobsnepal.com/jobs?page=2"


def test_tenders_on_the_listing_are_never_opened():
    page = scraper.parse_listing(read("listing.html"), LISTING_URL)

    # 144748 is an English EOI notice, 144742 a tender written in Nepali
    assert [i.external_id for i in page.items if worth_opening(i)] == ["144747", "144746"]


def test_empty_listing_page():
    page = scraper.parse_listing("<html><body><p>No jobs</p></body></html>", LISTING_URL)

    assert page.items == []
    assert page.next_url is None


def test_job_page_is_read_from_its_microdata():
    raw = scraper.parse_detail(read("job.html"), JOB)

    assert raw.title == "Admin/Finance Coordinator"
    assert raw.company == "National Federation of Women Living with HIV & AIDS"
    assert raw.location == "Kathmandu, Nepal"
    assert raw.experience == "5+ years"
    assert raw.deadline == "Apply before 18 Nov, 2026"
    assert raw.posted == "Job posted on 28 Oct, 2026"
    assert raw.salary is None  # this posting doesn't state a salary
    assert raw.description.startswith("Vacancy opening date- 29 October, 2026\n")
    assert "Duty Station: NFWLHA Central Office, Kathmandu" not in raw.description  # trimmed


def test_job_page_cleans_into_a_complete_job():
    raw = scraper.parse_detail(read("job.html"), JOB).model_copy(
        update={"scraped_at": datetime(2026, 10, 28, 12, 0, tzinfo=UTC)}
    )

    job = clean(raw)

    assert job.location == "Kathmandu"
    assert job.deadline == date(2026, 11, 18)
    assert (job.experience_min_years, job.experience_max_years) == (Decimal("5"), None)
    assert job.company_normalized_name == "national federation of women living with hiv and aids"


def test_experience_falls_back_to_the_description_when_the_field_has_no_number():
    html = (
        read("job.html")
        .replace("5+ years", "Please check vacancy details.")
        .replace(
            "Position: Admin/Finance Coordinator", "Minimum of 5 years of experience in finance"
        )
    )

    raw = scraper.parse_detail(html, JOB)

    assert (
        raw.experience
        == "Minimum of 5 years of experience in finance -1 (Treatment Care and Support Program)"
    )
