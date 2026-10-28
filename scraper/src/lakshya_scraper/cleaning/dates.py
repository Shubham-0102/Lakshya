"""Dates: AD dates, relative dates and Bikram Sambat (BS) dates -> datetime.date.

Nepali sites use both calendars. BS is about 56.7 years ahead of AD, so a year of 2070 or
later is read as BS (AD 2070 is decades away). Numeric dates are day/month, as in Nepal.
Relative dates ("5 days left") count from the scrape time in Nepal (UTC+5:45).
"""

import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import nepali_datetime

from lakshya_scraper.cleaning.text import ascii_digits, squash

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")
FIRST_BS_YEAR = 2070

_BS_MONTHS = {
    "baisakh": 1, "baishakh": 1, "vaisakh": 1, "बैशाख": 1, "वैशाख": 1,
    "jestha": 2, "jeth": 2, "जेठ": 2, "जेष्ठ": 2,
    "asar": 3, "ashadh": 3, "asadh": 3, "असार": 3, "आषाढ": 3,
    "shrawan": 4, "saun": 4, "sawan": 4, "साउन": 4, "श्रावण": 4,
    "bhadra": 5, "bhadau": 5, "भदौ": 5, "भाद्र": 5,
    "asoj": 6, "ashwin": 6, "aswin": 6, "असोज": 6, "आश्विन": 6,
    "kartik": 7, "kartika": 7, "कार्तिक": 7,
    "mangsir": 8, "mangshir": 8, "मंसिर": 8, "मङ्सिर": 8,
    "poush": 9, "paush": 9, "push": 9, "पुष": 9, "पौष": 9,
    "magh": 10, "माघ": 10,
    "falgun": 11, "fagun": 11, "phalgun": 11, "फागुन": 11, "फाल्गुन": 11,
    "chaitra": 12, "chait": 12, "चैत": 12, "चैत्र": 12,
}  # fmt: skip
_BS_MONTH = "|".join(sorted(map(re.escape, _BS_MONTHS), key=len, reverse=True))
# No \b around month names: \b doesn't work inside Devanagari words
_BS_MONTH_FIRST = re.compile(rf"({_BS_MONTH})\s*(\d{{1,2}})\s*,?\s*(\d{{4}})")
_BS_DAY_FIRST = re.compile(rf"(\d{{1,2}})\s*({_BS_MONTH})\s*,?\s*(\d{{4}})")

_LABEL = re.compile(
    r"^(application\s+)?(deadline|apply\s+(before|by)|closing\s+date|last\s+date(\s+to\s+apply)?"
    r"|expires?(\s+on)?|valid\s+(till|until))\s*[:\-]?\s*"
)
_COUNT_UNIT = r"(\d+|an?|one)\s+(day|week|month)s?"
_FROM_NOW = re.compile(
    rf"\bin\s+{_COUNT_UNIT}\b|\b{_COUNT_UNIT}\s+(?:from now|left|remaining|to go)\b"
)
_AGO = re.compile(rf"\b{_COUNT_UNIT}\s+ago\b")
# (?!\d) rather than \b at the end, so ISO timestamps like "2026-11-30T23:59:59" match too
_YEAR_FIRST = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")
_DAY_FIRST = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
_NAMED_AD = re.compile(r"\b([a-z]+\s+\d{1,2}\s+\d{4}|\d{1,2}\s+[a-z]+\s+\d{4})\b")
_AD_FORMATS = ["%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"]


def nepal_today(moment: datetime) -> date:
    """The date in Nepal at that moment. At 20:00 UTC it is already tomorrow in Nepal."""
    return moment.astimezone(NEPAL_TZ).date()


def parse_date(text: str, today: date) -> date | None:
    text = _LABEL.sub("", squash(ascii_digits(text.lower())))
    if not text:
        return None

    simple_words = {"today": 0, "tomorrow": 1, "yesterday": -1}
    if text in simple_words:
        return today + timedelta(days=simple_words[text])
    if match := _FROM_NOW.search(text):
        count, unit = match.group(1) or match.group(3), match.group(2) or match.group(4)
        return _shift(today, _count(count), unit)
    if match := _AGO.search(text):
        return _shift(today, -_count(match.group(1)), match.group(2))

    if match := _YEAR_FIRST.search(text):
        return _make_date(*map(int, match.groups()))
    if match := _DAY_FIRST.search(text):
        day, month, year = map(int, match.groups())
        return _make_date(year, month, day)

    if match := _BS_MONTH_FIRST.search(text):
        month_name, day, year = match.groups()
        return _bs_date(int(year), _BS_MONTHS[month_name], int(day))
    if match := _BS_DAY_FIRST.search(text):
        day, month_name, year = match.groups()
        return _bs_date(int(year), _BS_MONTHS[month_name], int(day))

    return _named_ad_date(text)


def _named_ad_date(text: str) -> date | None:
    """ "Oct 30, 2026", "18 Nov, 2026", "October 30th 2026" -> date."""
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\bsept\b", "sep", text.replace(",", " ").replace(".", " "))
    if not (match := _NAMED_AD.search(squash(text))):
        return None
    for fmt in _AD_FORMATS:
        try:
            return datetime.strptime(match.group(1), fmt).date()
        except ValueError:
            continue
    return None


def _make_date(year: int, month: int, day: int) -> date | None:
    if year >= FIRST_BS_YEAR:
        return _bs_date(year, month, day)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _bs_date(year: int, month: int, day: int) -> date | None:
    try:
        return nepali_datetime.date(year, month, day).to_datetime_date()
    except (ValueError, OverflowError, KeyError):
        return None  # e.g. day 32, or a year outside the library's calendar table


def _count(word: str) -> int:
    return int(word) if word.isdigit() else 1  # "a week", "an hour", "one day"


def _shift(start: date, count: int, unit: str) -> date:
    if unit == "day":
        return start + timedelta(days=count)
    if unit == "week":
        return start + timedelta(weeks=count)
    # Months: same day number, clamped to the month's length (Jan 31 + 1 month = Feb 28)
    month_index = start.month - 1 + count
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
