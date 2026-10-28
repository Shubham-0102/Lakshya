"""Database reads and writes for the pipeline."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from lakshya_backend.db.models import Company, Job, JobSource, Source
from lakshya_scraper.job_format import CleanJob, RawJob

# CleanJob fields that are not columns of the jobs table
_NOT_JOB_COLUMNS = {"source_slug", "external_id", "url", "company_name", "company_normalized_name"}


def known_external_ids(session: Session, source_id: int) -> set[str]:
    query = select(JobSource.external_id).where(JobSource.source_id == source_id)
    return set(session.scalars(query))


def mark_seen(session: Session, source_id: int, external_ids: list[str], seen_at: datetime) -> int:
    """Postings still on the listing: update last_seen_at instead of fetching them again."""
    if not external_ids:
        return 0
    job_ids = session.scalars(
        update(JobSource)
        .where(JobSource.source_id == source_id, JobSource.external_id.in_(external_ids))
        .values(last_seen_at=seen_at)
        .returning(JobSource.job_id),
        execution_options={"synchronize_session": False},
    ).all()
    session.execute(
        update(Job).where(Job.id.in_(job_ids)).values(last_seen_at=seen_at),
        execution_options={"synchronize_session": False},
    )
    return len(job_ids)


def get_or_create_company(session: Session, name: str, normalized_name: str) -> Company:
    # INSERT ... ON CONFLICT DO NOTHING is safe even if two runs add the same company at once
    session.execute(
        insert(Company)
        .values(name=name, normalized_name=normalized_name)
        .on_conflict_do_nothing(index_elements=["normalized_name"])
    )
    return session.scalars(select(Company).where(Company.normalized_name == normalized_name)).one()


def save_job(session: Session, source: Source, raw: RawJob, job: CleanJob) -> Job:
    """Store a new job, its company and the link back to the original posting."""
    company = get_or_create_company(session, job.company_name, job.company_normalized_name)
    columns = job.model_dump(exclude=_NOT_JOB_COLUMNS)
    columns["skills"] = list(job.skills)  # Postgres arrays come from lists, not tuples
    new_job = Job(company=company, **columns)
    session.add(
        JobSource(
            job=new_job,
            source=source,
            external_id=job.external_id,
            url=str(job.url),
            raw=raw.model_dump(mode="json"),  # kept so the job can be re-cleaned later
        )
    )
    session.flush()
    return new_job
