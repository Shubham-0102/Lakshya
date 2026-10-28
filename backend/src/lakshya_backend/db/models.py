from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lakshya_backend.db.base import Base, text_enum


class SourceType(StrEnum):
    PORTAL = "portal"
    CAREER_PAGE = "career_page"
    FEED = "feed"


class ComplianceStatus(StrEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"
    PENDING = "pending"


class HealthStatus(StrEnum):
    UNKNOWN = "unknown"  # never run
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # ran, but found zero jobs or missing fields
    FAILING = "failing"  # errors on recent runs


class SalaryPeriod(StrEnum):
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Source(TimestampMixin, Base):
    """A website we collect jobs from, or have reviewed and decided not to (see docs/sources.md)."""

    __tablename__ = "sources"
    __table_args__ = (
        # The scraping rules, enforced by the database rather than by convention
        CheckConstraint(
            "NOT enabled OR compliance_status = 'approved'", name="enabled_only_if_approved"
        ),
        CheckConstraint("crawl_delay_seconds >= 5", name="polite_crawl_delay"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    base_url: Mapped[str]
    type: Mapped[SourceType] = mapped_column(text_enum(SourceType, "type"))
    enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        text_enum(ComplianceStatus, "compliance_status"), server_default="pending"
    )
    compliance_notes: Mapped[str | None]
    crawl_delay_seconds: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    health_status: Mapped[HealthStatus] = mapped_column(
        text_enum(HealthStatus, "health_status"), server_default="unknown"
    )
    failure_count: Mapped[int] = mapped_column(server_default=text("0"))
    last_run_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]


class Company(TimestampMixin, Base):
    """An employer, merged across sources by normalized_name."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str]
    normalized_name: Mapped[str] = mapped_column(unique=True)
    website: Mapped[str | None]
    verified: Mapped[bool] = mapped_column(server_default=text("false"))

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(TimestampMixin, Base):
    """One unique job. A job seen on several sites has one row here and one JobSource per site."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range",
        ),
        CheckConstraint(
            "experience_min_years IS NULL OR experience_max_years IS NULL"
            " OR experience_min_years <= experience_max_years",
            name="experience_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # Postgres doesn't index foreign keys automatically, so the indexes are explicit
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str]
    normalized_title: Mapped[str]
    location: Mapped[str | None]
    is_remote: Mapped[bool] = mapped_column(server_default=text("false"))
    # Whole currency units (e.g. NPR 50000); salary_text keeps the original wording
    salary_min: Mapped[int | None]
    salary_max: Mapped[int | None]
    salary_currency: Mapped[str | None] = mapped_column(String(3))  # ISO 4217, e.g. NPR, USD
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(
        text_enum(SalaryPeriod, "salary_period")
    )
    salary_text: Mapped[str | None]
    experience_min_years: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    experience_max_years: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    deadline: Mapped[date | None] = mapped_column(index=True)
    description: Mapped[str | None]
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    company: Mapped[Company] = relationship(back_populates="jobs")
    job_sources: Mapped[list["JobSource"]] = relationship(back_populates="job")


class JobSource(Base):
    """One posting of a job on one source, with the link back to the original posting."""

    __tablename__ = "job_sources"
    __table_args__ = (
        # The same posting is stored once per source. This unique index also serves
        # lookups by source_id, because source_id is its first column.
        UniqueConstraint("source_id", "external_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str]  # the site's own job ID, or the URL slug if it has none
    url: Mapped[str]
    raw: Mapped[dict] = mapped_column(JSONB)  # the RawJob exactly as scraped, for re-cleaning
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped[Job] = relationship(back_populates="job_sources")
    source: Mapped[Source] = relationship()
