"""Initial schema: sources, companies, jobs and job_sources, plus the pgvector extension.

Revision ID: 0001
Revises:
Create Date: 2026-10-28 21:44:03.644907

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pgvector, for the embedding columns added in Phase 3
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "companies",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_companies_normalized_name")),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "portal",
                "career_page",
                "feed",
                name="type",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "compliance_status",
            sa.Enum(
                "approved",
                "blocked",
                "pending",
                name="compliance_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("compliance_notes", sa.Text(), nullable=True),
        sa.Column(
            "crawl_delay_seconds", sa.SmallInteger(), server_default=sa.text("5"), nullable=False
        ),
        sa.Column(
            "health_status",
            sa.Enum(
                "unknown",
                "healthy",
                "degraded",
                "failing",
                name="health_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "NOT enabled OR compliance_status = 'approved'",
            name=op.f("ck_sources_enabled_only_if_approved"),
        ),
        sa.CheckConstraint("crawl_delay_seconds >= 5", name=op.f("ck_sources_polite_crawl_delay")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("slug", name=op.f("uq_sources_slug")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("is_remote", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=True),
        sa.Column(
            "salary_period",
            sa.Enum(
                "hour",
                "day",
                "week",
                "month",
                "year",
                name="salary_period",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("salary_text", sa.Text(), nullable=True),
        sa.Column("experience_min_years", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("experience_max_years", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column(
            "skills", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "experience_min_years IS NULL OR experience_max_years IS NULL"
            " OR experience_min_years <= experience_max_years",
            name=op.f("ck_jobs_experience_range"),
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name=op.f("ck_jobs_salary_range"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_jobs_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_jobs_deadline"), "jobs", ["deadline"], unique=False)
    op.create_index(op.f("ix_jobs_last_seen_at"), "jobs", ["last_seen_at"], unique=False)
    op.create_table(
        "job_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_sources_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_job_sources_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_sources")),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_job_sources_source_id_external_id")
        ),
    )
    op.create_index(op.f("ix_job_sources_job_id"), "job_sources", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_sources_job_id"), table_name="job_sources")
    op.drop_table("job_sources")
    op.drop_index(op.f("ix_jobs_last_seen_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_deadline"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("sources")
    op.drop_table("companies")
    op.execute("DROP EXTENSION IF EXISTS vector")
