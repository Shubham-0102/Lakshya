"""Scheduled scraping: Beat calls dispatch_scrapes, which queues one task per source.

A failed run is not retried: the next scheduled run is the retry, which stays polite to a
site that is already struggling. The source's health shows that something went wrong.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lakshya_backend.db.models import ComplianceStatus, Source
from lakshya_backend.db.session import get_session
from lakshya_scraper.celery_app import app
from lakshya_scraper.pipeline import SourceBusy, run_source
from lakshya_scraper.scrapers import SCRAPERS

logger = logging.getLogger(__name__)

# A normal run tops out at 300 requests at 5 s each (25 minutes), plus page load time.
# Must stay below LOCK_TIMEOUT_SECONDS in pipeline.py.
SCRAPE_TIME_LIMIT_SECONDS = 50 * 60


def scrapable_slugs(session: Session) -> list[str]:
    query = (
        select(Source.slug, Source.last_run_at)
        .where(Source.enabled, Source.compliance_status == ComplianceStatus.APPROVED)
        .order_by(Source.slug)
    )
    now = datetime.now(UTC)
    due = []
    for slug, last_run in session.execute(query):
        if slug not in SCRAPERS:
            logger.warning("%s is enabled but has no scraper", slug)
        elif not last_run or now - last_run >= timedelta(
            hours=SCRAPERS[slug].min_hours_between_runs
        ):
            due.append(slug)
    return due


@app.task
def dispatch_scrapes() -> None:
    with get_session() as session:
        slugs = scrapable_slugs(session)
    for slug in slugs:
        scrape_source.delay(slug)
    logger.info("queued scrapes: %s", slugs)


@app.task(time_limit=SCRAPE_TIME_LIMIT_SECONDS)
def scrape_source(slug: str) -> None:
    try:
        run_source(slug)  # logs the result and records the source's health
    except SourceBusy as busy:
        logger.info("skipped: %s", busy)
