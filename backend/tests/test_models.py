import pytest
from sqlalchemy.exc import IntegrityError

from lakshya_backend.db.models import (
    Company,
    ComplianceStatus,
    HealthStatus,
    Job,
    JobSource,
    Source,
    SourceType,
)


def make_source(**overrides) -> Source:
    fields = {
        "slug": "example",
        "name": "Example Jobs",
        "base_url": "https://jobs.example.com",
        "type": SourceType.PORTAL,
        "compliance_status": ComplianceStatus.APPROVED,
        "enabled": True,
    } | overrides
    return Source(**fields)


def make_job(company: Company, **overrides) -> Job:
    fields = {
        "company": company,
        "title": "Backend Engineer",
        "normalized_title": "backend engineer",
    } | overrides
    return Job(**fields)


def test_source_gets_database_defaults(db_session):
    source = make_source(enabled=False, compliance_status=ComplianceStatus.PENDING)
    db_session.add(source)
    db_session.flush()

    assert source.crawl_delay_seconds == 5
    assert source.health_status == HealthStatus.UNKNOWN
    assert source.failure_count == 0


def test_job_with_source_link_round_trip(db_session):
    company = Company(name="Leapfrog Technology", normalized_name="leapfrog technology")
    source = make_source()
    job = make_job(company, skills=["python", "fastapi"])
    db_session.add(
        JobSource(
            job=job,
            source=source,
            external_id="2379506",
            url="https://jobs.example.com/2379506",
            raw={"title": "Backend Engineer"},
        )
    )
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(Job, job.id)
    assert stored.company.name == "Leapfrog Technology"
    assert stored.skills == ["python", "fastapi"]
    assert stored.job_sources[0].raw == {"title": "Backend Engineer"}
    assert stored.first_seen_at is not None


@pytest.mark.parametrize("status", [ComplianceStatus.BLOCKED, ComplianceStatus.PENDING])
def test_cannot_enable_a_source_that_is_not_approved(db_session, status):
    db_session.add(make_source(compliance_status=status, enabled=True))

    with pytest.raises(IntegrityError, match="ck_sources_enabled_only_if_approved"):
        db_session.flush()


def test_crawl_delay_cannot_go_below_five_seconds(db_session):
    db_session.add(make_source(crawl_delay_seconds=2))

    with pytest.raises(IntegrityError, match="ck_sources_polite_crawl_delay"):
        db_session.flush()


def test_same_posting_is_stored_once_per_source(db_session):
    company = Company(name="F1Soft", normalized_name="f1soft")
    source = make_source()
    for _ in range(2):
        db_session.add(
            JobSource(
                job=make_job(company),
                source=source,
                external_id="business-analyst-fonenxt",
                url="https://career.f1soft.com/jobs/business-analyst-fonenxt",
                raw={},
            )
        )

    with pytest.raises(IntegrityError, match="uq_job_sources_source_id_external_id"):
        db_session.flush()


def test_salary_min_cannot_exceed_max(db_session):
    company = Company(name="Acme", normalized_name="acme")
    db_session.add(make_job(company, salary_min=80_000, salary_max=50_000))

    with pytest.raises(IntegrityError, match="ck_jobs_salary_range"):
        db_session.flush()
