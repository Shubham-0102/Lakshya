"""At most one request per source every few seconds.

The "last request" marker lives in Redis, not in Python memory, so the limit holds even
when several Celery workers scrape the same source at once.
"""

import time
from collections.abc import Callable

from redis import Redis


def wait_for_turn(
    redis: Redis,
    key: str,
    delay_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Block until a request for `key` is allowed, then claim the slot. Returns seconds waited.

    SET ... NX PX succeeds only if the key doesn't exist, and the key expires after the
    delay. So the key existing means "someone made a request less than delay ago".
    """
    name = f"throttle:{key}"
    waited = 0.0
    while not redis.set(name, 1, nx=True, px=max(1, round(delay_seconds * 1000))):
        remaining_ms = redis.pttl(name)  # -2 if it just expired
        pause = max(remaining_ms, 10) / 1000
        sleep(pause)
        waited += pause
    return waited
