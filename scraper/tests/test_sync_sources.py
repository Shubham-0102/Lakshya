import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from lakshya_backend.db.models import ComplianceStatus, Source
from lakshya_scraper.sync_sources import SourceConfig, load_sources, sync_sources

EXAMPLE_YAML = """
sources:
  - slug: example
    name: Example Jobs
    base_url: https://jobs.example.com
    type: portal
    compliance_status: approved
    compliance_notes: test fixture
    enabled: true
"""


def write_yaml(tmp_path, content):
    path = tmp_path / "sources.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def all_sources(session):
    return session.scalars(select(Source).order_by(Source.slug)).all()


def test_first_sync_adds_and_second_sync_changes_nothing(db_session, tmp_path):
    configs = load_sources(write_yaml(tmp_path, EXAMPLE_YAML))

    assert sync_sources(db_session, configs) == (1, 0)
    assert sync_sources(db_session, configs) == (0, 0)
    assert [source.slug for source in all_sources(db_session)] == ["example"]


def test_changed_entry_updates_the_existing_row(db_session, tmp_path):
    sync_sources(db_session, load_sources(write_yaml(tmp_path, EXAMPLE_YAML)))
    changed_yaml = EXAMPLE_YAML.replace("enabled: true", "enabled: false")

    assert sync_sources(db_session, load_sources(write_yaml(tmp_path, changed_yaml))) == (0, 1)
    assert all_sources(db_session)[0].enabled is False


def test_database_rejects_enabling_a_blocked_source(db_session):
    blocked = SourceConfig(
        slug="blocked-site",
        name="Blocked",
        base_url="https://blocked.example.com",
        type="portal",
        compliance_status=ComplianceStatus.BLOCKED,
        compliance_notes="terms forbid scraping",
        enabled=True,
    )

    with pytest.raises(IntegrityError, match="ck_sources_enabled_only_if_approved"):
        sync_sources(db_session, [blocked])


def test_typo_in_yaml_is_caught_before_the_database(tmp_path):
    with pytest.raises(ValidationError, match="type"):
        load_sources(write_yaml(tmp_path, EXAMPLE_YAML.replace("type: portal", "type: portl")))


def test_real_sources_file_is_valid_and_only_approved_sources_are_enabled():
    configs = load_sources()

    assert {c.slug for c in configs if c.enabled} == {"jobsnepal", "f1soft", "leapfrog"}
    assert all(c.compliance_status == ComplianceStatus.APPROVED for c in configs if c.enabled)
