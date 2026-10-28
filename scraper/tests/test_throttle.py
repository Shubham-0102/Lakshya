import time
from uuid import uuid4

from redis import Redis

from lakshya_backend.config import get_settings
from lakshya_scraper.fetching.throttle import wait_for_turn


def test_first_request_does_not_wait(redis_client):
    assert wait_for_turn(redis_client, f"test-{uuid4()}", delay_seconds=0.3) == 0


def test_second_request_waits_for_the_delay(redis_client):
    key = f"test-{uuid4()}"
    wait_for_turn(redis_client, key, delay_seconds=0.3)

    started = time.monotonic()
    wait_for_turn(redis_client, key, delay_seconds=0.3)

    assert time.monotonic() - started >= 0.25


def test_different_sources_do_not_wait_for_each_other(redis_client):
    wait_for_turn(redis_client, f"test-{uuid4()}", delay_seconds=5)

    assert wait_for_turn(redis_client, f"test-{uuid4()}", delay_seconds=5) == 0


def test_limit_holds_across_separate_clients(redis_client):
    """Two workers = two Redis connections; the marker in Redis still makes one wait."""
    key = f"test-{uuid4()}"
    wait_for_turn(redis_client, key, delay_seconds=0.3)

    started = time.monotonic()
    with Redis.from_url(get_settings().redis_url) as other_worker:
        wait_for_turn(other_worker, key, delay_seconds=0.3)

    assert time.monotonic() - started >= 0.25
