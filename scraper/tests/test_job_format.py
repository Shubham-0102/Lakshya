import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from lakshya_backend.db.models import SalaryPeriod
from lakshya_scraper.job_format import CleanJob, RawJob

# Values copied exactly from https://career.f1soft.com/jobs/business-analyst-fonenxt
# (fetched 2026-10-28 during the source review)
F1SOFT_RAW = {
    "source_slug": "f1soft",
    "external_id": "business-analyst-fonenxt",
    "url": "https://career.f1soft.com/jobs/business-analyst-fonenxt",
    "title": "Business Analyst",
    "company": "FoneNXT",
    "location": "F1Soft Tower, Pulchowk, Lalitpur District, Nepal",
    "deadline": "Oct 30, 2026",
    "experience": "2-3 years of prior work experience in BA roles.",
    "scraped_at": datetime(2026, 10, 28, 10, 0, tzinfo=UTC),
}

CLEAN_MINIMUM = {
    "source_slug": "f1soft",
    "external_id": "business-analyst-fonenxt",
    "url": "https://career.f1soft.com/jobs/business-analyst-fonenxt",
    "title": "Business Analyst",
    "normalized_title": "business analyst",
    "company_name": "FoneNXT",
    "company_normalized_name": "fonenxt",
}


# --- RawJob -----------------------------------------------------------------------------


def test_real_f1soft_job_is_a_valid_raw_job():
    job = RawJob(**F1SOFT_RAW)

    assert job.title == "Business Analyst"
    assert job.deadline == "Oct 30, 2026"  # kept as text; the cleaner turns it into a date
    assert job.salary is None


def test_text_is_trimmed_and_blank_optional_fields_become_none():
    job = RawJob(**F1SOFT_RAW | {"title": "  Business Analyst \n", "salary": "   ", "posted": ""})

    assert job.title == "Business Analyst"
    assert job.salary is None
    assert job.posted is None


def test_blank_skills_are_dropped():
    job = RawJob(**F1SOFT_RAW | {"skills": [" SQL ", "", "  ", "Jira"]})

    assert job.skills == ("SQL", "Jira")


@pytest.mark.parametrize("field", ["source_slug", "external_id", "url", "title", "company"])
def test_required_fields_must_be_present(field):
    fields = {key: value for key, value in F1SOFT_RAW.items() if key != field}

    with pytest.raises(ValidationError, match=field):
        RawJob(**fields)


@pytest.mark.parametrize("field", ["title", "company", "external_id"])
def test_required_text_cannot_be_blank(field):
    with pytest.raises(ValidationError, match=field):
        RawJob(**F1SOFT_RAW | {field: "   "})


@pytest.mark.parametrize("url", ["not a url", "ftp://career.f1soft.com/jobs/1", ""])
def test_url_must_be_http_or_https(url):
    with pytest.raises(ValidationError, match="url"):
        RawJob(**F1SOFT_RAW | {"url": url})


def test_unknown_field_is_rejected():
    """A scraper typo like `titel` fails loudly instead of the title silently going missing."""
    with pytest.raises(ValidationError, match="titel"):
        RawJob(**F1SOFT_RAW | {"titel": "Business Analyst"})


def test_scraped_at_must_include_a_timezone():
    with pytest.raises(ValidationError, match="scraped_at"):
        RawJob(**F1SOFT_RAW | {"scraped_at": datetime(2026, 10, 28, 10, 0)})


def test_scraped_at_defaults_to_now_in_utc():
    fields = {key: value for key, value in F1SOFT_RAW.items() if key != "scraped_at"}

    assert RawJob(**fields).scraped_at.tzinfo is not None


def test_raw_job_survives_a_json_round_trip():
    """job_sources.raw stores RawJob as JSON; loading it back must give the same job."""
    job = RawJob(**F1SOFT_RAW | {"skills": ["SQL", "Jira"]})

    stored = json.loads(json.dumps(job.model_dump(mode="json")))

    assert RawJob.model_validate(stored) == job


# --- CleanJob ---------------------------------------------------------------------------


def test_cleaned_f1soft_job_is_valid():
    """What the task 6 cleaner should produce from F1SOFT_RAW."""
    job = CleanJob(
        **CLEAN_MINIMUM,
        location="Lalitpur",
        experience_min_years=Decimal("2"),
        experience_max_years=Decimal("3"),
        deadline=date(2026, 10, 30),
    )

    assert job.deadline == date(2026, 10, 30)
    assert job.is_remote is False
    assert job.skills == ()


def test_salary_fields_accept_a_normal_range():
    job = CleanJob(
        **CLEAN_MINIMUM,
        salary_min=50_000,
        salary_max=70_000,
        salary_currency="NPR",
        salary_period=SalaryPeriod.MONTH,
        salary_text="NPR 50,000 - 70,000 per month",
    )

    assert (job.salary_min, job.salary_max, job.salary_period) == (50_000, 70_000, "month")


def test_salary_min_cannot_exceed_max():
    with pytest.raises(ValidationError, match="salary_min is greater than salary_max"):
        CleanJob(**CLEAN_MINIMUM, salary_min=80_000, salary_max=50_000, salary_currency="NPR")


def test_salary_amount_needs_a_currency():
    with pytest.raises(ValidationError, match="needs a salary_currency"):
        CleanJob(**CLEAN_MINIMUM, salary_min=50_000)


@pytest.mark.parametrize("currency", ["npr", "RUPEES", "Rs", "N1R"])
def test_currency_must_be_a_three_letter_iso_code(currency):
    with pytest.raises(ValidationError, match="salary_currency"):
        CleanJob(**CLEAN_MINIMUM, salary_min=50_000, salary_currency=currency)


def test_salary_cannot_be_negative():
    with pytest.raises(ValidationError, match="salary_min"):
        CleanJob(**CLEAN_MINIMUM, salary_min=-1, salary_currency="NPR")


def test_experience_min_cannot_exceed_max():
    with pytest.raises(ValidationError, match="experience_min_years is greater"):
        CleanJob(
            **CLEAN_MINIMUM, experience_min_years=Decimal("5"), experience_max_years=Decimal("2")
        )


@pytest.mark.parametrize("years", [Decimal("100"), Decimal("1.25"), Decimal("-1")])
def test_experience_must_fit_the_database_column(years):
    """numeric(3,1) holds 0.0 to 99.9 with one decimal place."""
    with pytest.raises(ValidationError, match="experience_min_years"):
        CleanJob(**CLEAN_MINIMUM, experience_min_years=years)
