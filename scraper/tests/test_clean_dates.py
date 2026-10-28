from datetime import UTC, date, datetime

import pytest

from lakshya_scraper.cleaning.dates import nepal_today, parse_date

TODAY = date(2026, 10, 28)  # BS 2083-07-11


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Real, from the sources
        ("Oct 30, 2026", date(2026, 10, 30)),  # F1Soft job page
        ("Deadline: Nov 15, 2026", date(2026, 11, 15)),  # F1Soft listing
        ("Apply before 18 Nov, 2026", date(2026, 11, 18)),  # jobsnepal
        ("2 weeks from now", date(2026, 11, 11)),  # F1Soft listing
        ("1 day from now", date(2026, 10, 29)),  # F1Soft listing
        # Other AD formats
        ("30 October 2026", date(2026, 10, 30)),
        ("October 30th, 2026", date(2026, 10, 30)),
        ("Sept 3, 2026", date(2026, 9, 3)),
        ("2026-11-18", date(2026, 11, 18)),
        ("18/11/2026", date(2026, 11, 18)),
        ("18.11.2026", date(2026, 11, 18)),
        ("05/11/2026", date(2026, 11, 5)),  # ambiguous: read as day/month, as in Nepal
        # Relative to today
        ("today", TODAY),
        ("tomorrow", date(2026, 10, 29)),
        ("5 days left", date(2026, 11, 2)),
        ("in 3 days", date(2026, 10, 31)),
        ("a month from now", date(2026, 11, 28)),
        ("3 days ago", date(2026, 10, 25)),
        # Bikram Sambat, including the known New Year anchors
        ("2083-07-15", date(2026, 11, 1)),
        ("२०८३/०७/१५", date(2026, 11, 1)),  # Devanagari digits
        ("15/07/2083", date(2026, 11, 1)),
        ("Kartik 15, 2083", date(2026, 11, 1)),
        ("15 Kartik 2083", date(2026, 11, 1)),
        ("१५ कार्तिक २०८३", date(2026, 11, 1)),
        ("2080-01-01", date(2023, 4, 14)),
        ("2081-01-01", date(2024, 4, 13)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text, TODAY) == expected


@pytest.mark.parametrize("text", ["garbage", "", "Deadline:", "2083-13-40", "31/02/2026"])
def test_unparseable_or_impossible_dates_give_none(text):
    assert parse_date(text, TODAY) is None


def test_month_arithmetic_clamps_to_the_end_of_the_month():
    assert parse_date("1 month from now", date(2026, 1, 31)) == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("utc_time", "nepal_date"),
    [
        (datetime(2026, 10, 28, 18, 14, tzinfo=UTC), date(2026, 10, 28)),  # 23:59 in Nepal
        (datetime(2026, 10, 28, 18, 15, tzinfo=UTC), date(2026, 10, 29)),  # 00:00 in Nepal
        (datetime(2026, 10, 28, 20, 0, tzinfo=UTC), date(2026, 10, 29)),
    ],
)
def test_nepal_today_uses_nepal_time_not_utc(utc_time, nepal_date):
    """Nepal is UTC+5:45, so "today" changes at 18:15 UTC."""
    assert nepal_today(utc_time) == nepal_date
