import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from lakshya_scraper.cleaning import clean
from lakshya_scraper.job_format import CleanJob, RawJob

# The same real F1Soft posting as in test_job_format.py
F1SOFT_RAW = RawJob(
    source_slug="f1soft",
    external_id="business-analyst-fonenxt",
    url="https://career.f1soft.com/jobs/business-analyst-fonenxt",
    title="Business Analyst",
    company="FoneNXT",
    location="F1Soft Tower, Pulchowk, Lalitpur District, Nepal",
    deadline="Oct 30, 2026",
    experience="2-3 years of prior work experience in BA roles.",
    scraped_at=datetime(2026, 10, 28, 10, 0, tzinfo=UTC),
)


def leapfrog_raw(**overrides) -> RawJob:
    fields = {
        "source_slug": "leapfrog",
        "external_id": "2379506",
        "url": "https://career.lftechnology.com/o/senior-full-stack-developer-3",
        "title": "Senior Full-Stack Developer",
        "company": "Leapfrog Technology",
        "location": "Kathmandu, Nepal",
        "scraped_at": datetime(2026, 10, 28, 10, 0, tzinfo=UTC),
    } | overrides
    return RawJob(**fields)


def test_real_f1soft_job_cleans_to_the_expected_clean_job():
    assert clean(F1SOFT_RAW) == CleanJob(
        source_slug="f1soft",
        external_id="business-analyst-fonenxt",
        url="https://career.f1soft.com/jobs/business-analyst-fonenxt",
        title="Business Analyst",
        normalized_title="business analyst",
        company_name="FoneNXT",
        company_normalized_name="fonenxt",
        location="Lalitpur",
        experience_min_years=Decimal("2"),
        experience_max_years=Decimal("3"),
        deadline=date(2026, 10, 30),
    )


def test_tender_is_skipped():
    tender = leapfrog_raw(title="CALL FOR EXPRESSION OF INTEREST (EOI)")

    assert clean(tender) is None


def test_onsite_job_outside_nepal_is_skipped():
    assert clean(leapfrog_raw(location="Pune, India")) is None


def test_remote_job_limited_to_another_country_is_skipped():
    assert clean(leapfrog_raw(location="Remote (India)")) is None


def test_remote_job_limited_to_an_unknown_place_is_skipped():
    assert clean(leapfrog_raw(location="Remote - Boston")) is None  # real, Remote OK


def test_remote_job_open_to_nepal_is_kept():
    job = clean(leapfrog_raw(location="Remote - Worldwide"))

    assert job.is_remote
    assert job.location is None


def test_salary_is_parsed_and_original_wording_kept():
    job = clean(leapfrog_raw(salary="NPR 1,50,000 - 2,00,000 per month"))

    assert (job.salary_min, job.salary_max, job.salary_currency) == (150_000, 200_000, "NPR")
    assert job.salary_text == "NPR 1,50,000 - 2,00,000 per month"


def test_negotiable_salary_keeps_only_the_text():
    job = clean(leapfrog_raw(salary="Negotiable"))

    assert job.salary_min is None
    assert job.salary_text == "Negotiable"


def test_skills_are_lowercased_and_deduplicated():
    job = clean(leapfrog_raw(skills=["Python", "FastAPI", "python", "React"]))

    assert job.skills == ("python", "fastapi", "react")


def test_relative_deadline_counts_from_the_date_in_nepal():
    # 20:00 UTC on Oct 28 is already Oct 29 in Nepal, so "1 day from now" is Oct 30
    raw = leapfrog_raw(
        deadline="1 day from now", scraped_at=datetime(2026, 10, 28, 20, 0, tzinfo=UTC)
    )

    assert clean(raw).deadline == date(2026, 10, 30)


def test_unparseable_values_become_none_and_are_logged(caplog):
    raw = leapfrog_raw(deadline="whenever", salary="NPR ???", location="Province 1")

    with caplog.at_level(logging.INFO, logger="lakshya_scraper.cleaning.clean"):
        job = clean(raw)

    assert job.deadline is None
    assert job.location == "Province 1"
    assert "could not parse deadline 'whenever'" in caplog.text
    assert "unrecognized location kept as text ('Province 1')" in caplog.text


def test_text_garbled_on_the_way_to_us_is_repaired():
    job = clean(
        leapfrog_raw(
            title="Oracle Lead \xe2\x80\x93 Logistics",  # real shape, Remote OK
            company="Caf\xc3\xa9 Labs",
            description="Ciudad de M\xc3\xa9xico",
        )
    )

    assert job.title == "Oracle Lead – Logistics"
    assert job.company_name == "Café Labs"
    assert job.description == "Ciudad de México"


def test_text_that_is_fine_is_left_alone():
    job = clean(leapfrog_raw(title="Développeur – पोखरा"))

    assert job.title == "Développeur – पोखरा"


def test_pay_that_cannot_be_yearly_keeps_only_its_wording():
    job = clean(leapfrog_raw(salary="USD 40 - 48 per year"))  # real: hourly, labelled yearly

    assert (job.salary_min, job.salary_max, job.salary_period) == (None, None, None)
    assert job.salary_text == "USD 40 - 48 per year"


def test_real_yearly_pay_is_kept():
    job = clean(leapfrog_raw(salary="USD 55000 - 70000 per year"))

    assert (job.salary_min, job.salary_max) == (55_000, 70_000)


def test_low_yearly_pay_in_rupees_is_not_treated_as_mislabelled():
    job = clean(leapfrog_raw(salary="NPR 4,000 per year"))

    assert job.salary_max == 4_000
