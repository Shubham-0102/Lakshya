from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from lakshya_backend.db.models import ComplianceStatus, Source, SourceType
from lakshya_scraper import pipeline, tasks
from lakshya_scraper.celery_app import app
from lakshya_scraper.pipeline import LOCK_TIMEOUT_SECONDS, SourceBusy, run_source, source_lock
from lakshya_scraper.scrapers import SCRAPERS


def add_source(session, slug, enabled=True, status=ComplianceStatus.APPROVED, last_run_at=None):
    session.add(
        Source(
            slug=slug,
            name=slug,
            base_url=f"https://{slug}.example.com",
            type=SourceType.PORTAL,
            compliance_status=status,
            enabled=enabled,
            last_run_at=last_run_at,
        )
    )
    session.flush()


def hours_ago(hours):
    return datetime.now(UTC) - timedelta(hours=hours)


class ChangesDaily:
    min_hours_between_runs = 20


def test_only_enabled_approved_sources_with_a_scraper_are_scraped(db_session, monkeypatch):
    monkeypatch.setitem(SCRAPERS, "ready", object)
    monkeypatch.setitem(SCRAPERS, "switched-off", object)
    monkeypatch.setitem(SCRAPERS, "blocked", object)
    add_source(db_session, "ready")
    add_source(db_session, "switched-off", enabled=False)
    add_source(db_session, "blocked", enabled=False, status=ComplianceStatus.BLOCKED)
    add_source(db_session, "no-scraper-yet")

    assert tasks.scrapable_slugs(db_session) == ["ready"]


def test_source_that_changes_daily_is_not_scraped_twice_a_day(db_session, monkeypatch):
    monkeypatch.setitem(SCRAPERS, "ran-this-morning", ChangesDaily)
    monkeypatch.setitem(SCRAPERS, "ran-yesterday", ChangesDaily)
    monkeypatch.setitem(SCRAPERS, "never-ran", ChangesDaily)
    add_source(db_session, "ran-this-morning", last_run_at=hours_ago(12))
    add_source(db_session, "ran-yesterday", last_run_at=hours_ago(24))
    add_source(db_session, "never-ran")

    assert tasks.scrapable_slugs(db_session) == ["never-ran", "ran-yesterday"]


def test_other_sources_run_on_every_schedule(db_session, monkeypatch):
    class AnySource:
        min_hours_between_runs = 0

    monkeypatch.setitem(SCRAPERS, "ran-recently", AnySource)
    add_source(db_session, "ran-recently", last_run_at=hours_ago(1))

    assert tasks.scrapable_slugs(db_session) == ["ran-recently"]


def test_dispatch_queues_one_task_per_source(monkeypatch):
    queued = []
    monkeypatch.setattr(tasks, "get_session", lambda: _NoSession())
    monkeypatch.setattr(tasks, "scrapable_slugs", lambda session: ["f1soft", "jobsnepal"])
    monkeypatch.setattr(tasks.scrape_source, "delay", queued.append)

    tasks.dispatch_scrapes()

    assert queued == ["f1soft", "jobsnepal"]


class _NoSession:
    def __enter__(self):
        return None

    def __exit__(self, *exc_info):
        return False


def test_schedule_is_twice_a_day_in_nepal_time():
    assert app.conf.timezone == "Asia/Kathmandu"
    entry = app.conf.beat_schedule["scrape-all-sources"]
    assert entry["task"] == tasks.dispatch_scrapes.name
    assert entry["schedule"].hour == {6, 18}
    assert entry["schedule"].minute == {0}


def test_a_running_task_cannot_outlive_its_lock():
    assert tasks.scrape_source.time_limit < LOCK_TIMEOUT_SECONDS


def test_task_runs_the_source(monkeypatch):
    runs = []
    monkeypatch.setattr(tasks, "run_source", runs.append)

    tasks.scrape_source("jobsnepal")

    assert runs == ["jobsnepal"]


def test_task_skips_a_busy_source(monkeypatch):
    def busy(slug):
        raise SourceBusy(f"{slug} is already being scraped")

    monkeypatch.setattr(tasks, "run_source", busy)

    tasks.scrape_source("jobsnepal")  # no exception: the run in progress carries on


def test_a_held_lock_stops_a_second_run(redis_client):
    slug = f"test-{uuid4()}"
    with source_lock(redis_client, slug):
        with pytest.raises(SourceBusy):
            with source_lock(redis_client, slug):
                pytest.fail("two runs of one source must not overlap")


def test_different_sources_do_not_block_each_other(redis_client):
    with source_lock(redis_client, f"test-{uuid4()}"):
        with source_lock(redis_client, f"test-{uuid4()}"):
            pass


def test_lock_is_released_after_a_run_crashes(redis_client):
    slug = f"test-{uuid4()}"
    with pytest.raises(RuntimeError):
        with source_lock(redis_client, slug):
            raise RuntimeError("the run died")

    with source_lock(redis_client, slug):
        pass  # the next run can start


def test_lock_expires_on_its_own_if_a_worker_is_killed(redis_client):
    slug = f"test-{uuid4()}"
    with source_lock(redis_client, slug):
        ttl = redis_client.ttl(f"lock:source:{slug}")

    assert 0 < ttl <= LOCK_TIMEOUT_SECONDS


def test_run_source_does_not_start_while_the_source_is_locked(redis_client, monkeypatch):
    slug = f"test-{uuid4()}"
    monkeypatch.setitem(SCRAPERS, slug, object)
    monkeypatch.setattr(
        pipeline, "get_session", lambda: pytest.fail("a busy source must not start a run")
    )

    with source_lock(redis_client, slug):
        with pytest.raises(SourceBusy):
            run_source(slug)
