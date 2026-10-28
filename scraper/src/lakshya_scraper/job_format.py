"""The two job formats the whole pipeline agrees on.

RawJob:   what every scraper outputs (and, in Phase 2, the AI extraction too). Text exactly
          as it appears on the page: scrapers extract, they never interpret.
CleanJob: what the cleaner outputs and the database writer accepts. One field per column
          of the jobs table, plus the source fields stored in job_sources.

Flow: scraper -> RawJob -> clean() -> CleanJob -> database (RawJob is also kept as JSON).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from lakshya_backend.db.models import SalaryPeriod


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
    return value or None


def _drop_blank(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(stripped for value in values if (stripped := value.strip()))


# Trimmed, and must not be empty after trimming
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# Trimmed; an empty or whitespace-only string becomes None
OptionalText = Annotated[str | None, BeforeValidator(_blank_to_none)]
# Trimmed; blank items are dropped
TextList = Annotated[tuple[str, ...], AfterValidator(_drop_blank)]
# Mirrors numeric(3,1) in the database: 0.0 to 99.9
Years = Annotated[Decimal, Field(ge=0, max_digits=3, decimal_places=1)]


class RawJob(BaseModel):
    """One job as a scraper found it. Every text field is copied from the page unchanged."""

    # extra="forbid": a typo like `titel=` fails loudly instead of being silently ignored
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_slug: RequiredText
    external_id: RequiredText  # the site's job ID, or the URL slug if it has none
    url: HttpUrl  # link back to the original posting
    title: RequiredText
    company: RequiredText
    location: OptionalText = None  # e.g. "F1Soft Tower, Pulchowk, Lalitpur District, Nepal"
    salary: OptionalText = None  # e.g. "NPR 50,000 - 70,000 per month", "Negotiable"
    experience: OptionalText = None  # e.g. "2+ years", "Fresher"
    deadline: OptionalText = None  # e.g. "Oct 30, 2026", "2 weeks from now", "2083-07-15"
    posted: OptionalText = None  # e.g. "28 Oct, 2026"
    description: OptionalText = None
    skills: TextList = ()
    scraped_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class CleanJob(BaseModel):
    """One job after cleaning: typed, normalized and ready to store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Where it came from (stored in job_sources)
    source_slug: RequiredText
    external_id: RequiredText
    url: HttpUrl

    # The job itself (stored in jobs and companies)
    title: RequiredText
    normalized_title: RequiredText
    company_name: RequiredText
    company_normalized_name: RequiredText
    location: OptionalText = None
    is_remote: bool = False
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    salary_period: SalaryPeriod | None = None
    salary_text: OptionalText = None  # original wording, e.g. "Negotiable"
    experience_min_years: Years | None = None
    experience_max_years: Years | None = None
    skills: TextList = ()
    deadline: date | None = None
    description: OptionalText = None

    @model_validator(mode="after")
    def check_ranges(self) -> Self:
        # The same rules as the database CHECK constraints, caught earlier with a clearer message
        if None not in (self.salary_min, self.salary_max) and self.salary_min > self.salary_max:
            raise ValueError("salary_min is greater than salary_max")
        if (
            self.salary_min is not None or self.salary_max is not None
        ) and not self.salary_currency:
            raise ValueError("a salary amount needs a salary_currency")
        min_years, max_years = self.experience_min_years, self.experience_max_years
        if None not in (min_years, max_years) and min_years > max_years:
            raise ValueError("experience_min_years is greater than experience_max_years")
        return self
