"""clean(): RawJob -> CleanJob, or None for postings we don't keep."""

import logging
import re

from lakshya_scraper.cleaning.companies import clean_company_name, normalize_company
from lakshya_scraper.cleaning.dates import nepal_today, parse_date
from lakshya_scraper.cleaning.experience import parse_experience
from lakshya_scraper.cleaning.locations import Location, clean_location
from lakshya_scraper.cleaning.salaries import NO_SALARY, parse_salary
from lakshya_scraper.cleaning.titles import clean_title, is_job_posting, normalize_title
from lakshya_scraper.job_format import CleanJob, RawJob

logger = logging.getLogger(__name__)

_NO_LOCATION = Location(None, is_remote=False, outside_nepal=False, recognized=True)


def clean(raw: RawJob) -> CleanJob | None:
    """Returns None for tenders and notices, and for on-site jobs outside Nepal."""
    job = f"{raw.source_slug}/{raw.external_id}"

    if not is_job_posting(raw.title):
        logger.info("%s skipped: not a job posting (%r)", job, raw.title)
        return None

    location = clean_location(raw.location) if raw.location else _NO_LOCATION
    if location.outside_nepal and not location.is_remote:
        logger.info("%s skipped: outside Nepal and not remote (%r)", job, raw.location)
        return None
    if not location.recognized:
        logger.info("%s: unrecognized location kept as text (%r)", job, raw.location)

    salary = parse_salary(raw.salary) if raw.salary else NO_SALARY
    if raw.salary and salary == NO_SALARY and _has_digit(raw.salary):
        logger.warning("%s: could not parse salary %r", job, raw.salary)

    min_years, max_years = parse_experience(raw.experience) if raw.experience else (None, None)
    if raw.experience and min_years is None and max_years is None and _has_digit(raw.experience):
        logger.warning("%s: could not parse experience %r", job, raw.experience)

    deadline = parse_date(raw.deadline, nepal_today(raw.scraped_at)) if raw.deadline else None
    if raw.deadline and deadline is None:
        logger.warning("%s: could not parse deadline %r", job, raw.deadline)

    title = clean_title(raw.title)
    return CleanJob(
        source_slug=raw.source_slug,
        external_id=raw.external_id,
        url=raw.url,
        title=title,
        normalized_title=normalize_title(title),
        company_name=clean_company_name(raw.company),
        company_normalized_name=normalize_company(raw.company),
        location=location.name,
        is_remote=location.is_remote,
        salary_min=salary.min,
        salary_max=salary.max,
        salary_currency=salary.currency,
        salary_period=salary.period,
        salary_text=raw.salary,
        experience_min_years=min_years,
        experience_max_years=max_years,
        skills=tuple(dict.fromkeys(skill.lower() for skill in raw.skills)),  # dedupe, keep order
        deadline=deadline,
        description=raw.description,
    )


def _has_digit(text: str) -> bool:
    return bool(re.search(r"\d|[०-९]", text))
