"""Re-run clean() on the saved raw records, so cleaning fixes reach jobs saved earlier.

Nothing is fetched: this only reads job_sources.raw. Relative deadlines stay correct because
the raw record keeps the date it was scraped.

A job cleaning now rejects is removed if it came from a feed: feeds are re-read on every run
and the same rule then skips it. A job from a page stays and is reported, because removing it
would make every later run fetch that page again.

A job with several sources (Phase 2) would be overwritten by each of them in turn. In
Phase 1 every job has exactly one.
"""

from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from lakshya_backend.db.models import Job, JobSource, SourceType
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
    rejected: list[str] = field(default_factory=list)  # URLs of jobs cleaning would now skip
    removed: int = 0  # of those, the jobs from feeds: removed unless it's a dry run
    changes: list[Change] = field(default_factory=list)


def reclean(session: Session, dry_run: bool = False) -> RecleanResult:
    result = RecleanResult()
    postings = session.scalars(
        select(JobSource)
        .options(joinedload(JobSource.job).joinedload(Job.company), joinedload(JobSource.source))
        .order_by(JobSource.id)
    ).all()

    for posting in postings:
        result.checked += 1
        cleaned = clean(RawJob.model_validate(posting.raw))
        if cleaned is None:
            result.rejected.append(posting.url)
            if posting.source.type == SourceType.FEED:
                session.execute(delete(Job).where(Job.id == posting.job_id))
                result.removed += 1
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
