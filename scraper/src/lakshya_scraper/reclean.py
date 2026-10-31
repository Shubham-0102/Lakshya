"""Re-run clean() on the saved raw records, so cleaning fixes reach jobs saved earlier.

Nothing is fetched: this only reads job_sources.raw. Relative deadlines stay correct because
the raw record keeps the date it was scraped.

A job with several sources (Phase 2) would be overwritten by each of them in turn. In
Phase 1 every job has exactly one.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from lakshya_backend.db.models import Job, JobSource
from lakshya_scraper.cleaning import clean
from lakshya_scraper.job_format import RawJob
from lakshya_scraper.storage import get_or_create_company, job_columns


@dataclass
class Change:
    job_id: int
    url: str
    field: str
    old: object
    new: object


@dataclass
class RecleanResult:
    checked: int = 0
    changed: int = 0  # jobs with at least one field changed
    # URLs of jobs cleaning would now skip. They are reported, not deleted: without the
    # job_sources row the next run would treat them as new and fetch them every time.
    rejected: list[str] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)


def reclean(session: Session, dry_run: bool = False) -> RecleanResult:
    result = RecleanResult()
    postings = session.scalars(
        select(JobSource)
        .options(joinedload(JobSource.job).joinedload(Job.company))
        .order_by(JobSource.id)
    ).all()

    for posting in postings:
        result.checked += 1
        cleaned = clean(RawJob.model_validate(posting.raw))
        if cleaned is None:
            result.rejected.append(posting.url)
            continue

        job = posting.job
        changes = []
        for name, new in job_columns(cleaned).items():
            old = getattr(job, name)
            if old != new:
                changes.append(Change(job.id, posting.url, name, old, new))
                setattr(job, name, new)

        if job.company.normalized_name != cleaned.company_normalized_name:
            company = get_or_create_company(
                session, cleaned.company_name, cleaned.company_normalized_name
            )
            changes.append(Change(job.id, posting.url, "company", job.company.name, company.name))
            job.company = company

        result.changed += bool(changes)
        result.changes += changes

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return result
