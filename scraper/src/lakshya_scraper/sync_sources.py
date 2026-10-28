"""Load scraper/sources.yaml into the sources table.

Run:  uv run python -m lakshya_scraper.sync_sources

Safe to re-run: sources are matched by slug, new ones are inserted and changed
ones updated. Sources missing from the file are left alone (job_sources rows
may still point at them); disable a source by setting enabled: false.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from lakshya_backend.db.models import ComplianceStatus, Source, SourceType
from lakshya_backend.db.session import get_session

SOURCES_FILE = Path(__file__).resolve().parents[2] / "sources.yaml"


class SourceConfig(BaseModel):
    """One entry in sources.yaml. Validates the file before anything touches the database."""

    slug: str
    name: str
    base_url: str
    type: SourceType
    compliance_status: ComplianceStatus
    compliance_notes: str
    enabled: bool = False
    crawl_delay_seconds: int = 5


def load_sources(path: Path = SOURCES_FILE) -> list[SourceConfig]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SourceConfig(**entry) for entry in data["sources"]]


def sync_sources(session: Session, configs: list[SourceConfig]) -> tuple[int, int]:
    """Insert new sources and update changed ones. Returns (added, updated)."""
    existing = {source.slug: source for source in session.scalars(select(Source))}
    added = updated = 0

    for config in configs:
        values = config.model_dump()
        source = existing.get(config.slug)
        if source is None:
            session.add(Source(**values))
            added += 1
            continue

        changed = {
            field: value for field, value in values.items() if getattr(source, field) != value
        }
        for field, value in changed.items():
            setattr(source, field, value)
        updated += bool(changed)

    session.flush()
    return added, updated


def main() -> None:
    configs = load_sources()
    with get_session() as session, session.begin():
        added, updated = sync_sources(session, configs)
    enabled = sum(config.enabled for config in configs)
    print(f"{len(configs)} sources ({enabled} enabled): {added} added, {updated} updated")


if __name__ == "__main__":
    main()
