"""The Celery app: Redis as the message broker, and the timetable Beat follows.

celery -A lakshya_scraper.celery_app worker --loglevel=INFO
celery -A lakshya_scraper.celery_app beat --loglevel=INFO
"""

from celery import Celery
from celery.schedules import crontab

from lakshya_backend.config import get_settings

app = Celery("lakshya_scraper", broker=get_settings().redis_url, include=["lakshya_scraper.tasks"])

app.conf.update(
    timezone="Asia/Kathmandu",
    broker_connection_retry_on_startup=True,
    # Results go to the logs and the sources table, so tasks store nothing in Redis
    task_ignore_result=True,
    # Each run holds a Chromium, so only a few run at once. They are different sites,
    # and each site still gets at most one request every few seconds.
    worker_concurrency=2,
    # Take a task only when free, so a long run can't hold another source's task back
    worker_prefetch_multiplier=1,
    beat_schedule={
        "scrape-all-sources": {
            "task": "lakshya_scraper.tasks.dispatch_scrapes",
            "schedule": crontab(hour="6,18", minute=0),
        },
    },
)
