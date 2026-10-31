"""reclean against the real test database, with jobs saved the way the pipeline saves them."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from lakshya_backend.db.models import Company, ComplianceStatus, Job, Source, SourceType
from lakshya_scraper import __main__ as cli
from lakshya_scraper.cleaning import clean
from lakshya_scraper.job_format import RawJob
from lakshya_scraper.reclean import reclean
from lakshya_scraper.storage import save_job


@pytest.fixture
def source(db_session):
    example = Source(
        slug="example",
        name="Example Jobs",
        base_url="https://jobs.example.com",
        type=SourceType.PORTAL,
        compliance_status=ComplianceStatus.APPROVED,
        enabled=True,
    )
    db_session.add(example)
    db_session.commit()
    return example


def raw_job(external_id="1", **fields) -> RawJob:
    defaults = {
        "title": "Backend Engineer",
        "company": "Acme Pvt. Ltd.",
        "location": "Kathmandu",
        "salary": "NPR 50,000 - 70,000 per month",
        "experience": "5+ years",
        "deadline": "Nov 30, 2026",
        "skills": ("Python", "FastAPI"),
        "description": "Build APIs.",
    }
    return RawJob(
        source_slug="example",
        external_id=external_id,
        url=f"https://jobs.example.com/jobs/{external_id}",
        **(defaults | fields),
    )


def save(session, source, raw: RawJob, **stale_values) -> Job:
    """Save a job as the pipeline would, then overwrite fields to imitate an older cleaner."""
    job = save_job(session, source, raw, clean(raw))
    for name, value in stale_values.items():
        setattr(job, name, value)
    session.commit()
    return job


def test_a_stale_field_is_fixed_from_the_raw_text(db_session, source):
    job = save(db_session, source, raw_job(), experience_min_years=Decimal(2))

    result = reclean(db_session)

    db_session.refresh(job)
    assert job.experience_min_years == 5
    assert (result.checked, result.changed) == (1, 1)
    assert [(c.field, c.old, c.new) for c in result.changes] == [
        ("experience_min_years", Decimal(2), Decimal(5))
    ]


def test_up_to_date_jobs_are_left_alone(db_session, source):
    """Every field must compare equal after a trip through the database (Decimal, enum, date)."""
    save(db_session, source, raw_job())

    result = reclean(db_session)

    assert (result.checked, result.changed, result.changes) == (1, 0, [])


def test_running_twice_changes_nothing_the_second_time(db_session, source):
    save(db_session, source, raw_job(), location="Other - Specify")

    assert reclean(db_session).changed == 1
    assert reclean(db_session).changed == 0


def test_dry_run_reports_changes_but_saves_nothing(db_session, source):
    job = save(db_session, source, raw_job(), experience_min_years=Decimal(2))

    result = reclean(db_session, dry_run=True)

    assert result.changed == 1
    db_session.refresh(job)
    assert job.experience_min_years == 2


def test_a_job_moves_to_the_right_company(db_session, source):
    job = save(db_session, source, raw_job())
    wrong = Company(name="Old Name", normalized_name="old name")
    job.company = wrong
    db_session.commit()

    result = reclean(db_session)

    db_session.refresh(job)
    assert job.company.normalized_name == "acme"
    assert result.changes[0].field == "company"


def test_dry_run_does_not_create_a_company(db_session, source):
    job = save(db_session, source, raw_job())
    job.company = Company(name="Old Name", normalized_name="old name")
    db_session.commit()
    db_session.delete(db_session.scalars(select(Company).filter_by(normalized_name="acme")).one())
    db_session.commit()

    reclean(db_session, dry_run=True)

    count = select(func.count()).select_from(Company).filter_by(normalized_name="acme")
    assert db_session.scalar(count) == 0


def test_a_job_cleaning_now_rejects_is_kept_and_reported(db_session, source):
    raw = raw_job()
    job = save(db_session, source, raw)
    # Imitate a stored posting that today's cleaner treats as a tender
    job.job_sources[0].raw = raw_job(title="Call for Bid").model_dump(mode="json")
    db_session.commit()

    result = reclean(db_session)

    assert result.rejected == [str(raw.url)]
    assert result.changed == 0
    assert db_session.scalar(select(func.count()).select_from(Job)) == 1


def test_relative_deadlines_use_the_day_the_job_was_scraped(db_session, source):
    scraped = datetime(2026, 1, 1, 6, tzinfo=UTC)
    raw = raw_job(deadline="5 days left", scraped_at=scraped)
    job = save(db_session, source, raw, deadline=date(2020, 1, 1))

    reclean(db_session)

    db_session.refresh(job)
    assert job.deadline == date(2026, 1, 6)


def test_command_line_prints_the_changes(db_session, source, monkeypatch, capsys):
    save(db_session, source, raw_job(), experience_min_years=Decimal(2))
    monkeypatch.setattr(cli, "get_session", lambda: _KeepOpen(db_session))

    assert cli.main(["reclean", "--dry-run"]) == 0

    output = capsys.readouterr().out
    assert '"changed": 1' in output
    assert '"field": "experience_min_years"' in output


class _KeepOpen:
    """`with get_session()` closes its session; the test's session must stay open."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc_info):
        return False
