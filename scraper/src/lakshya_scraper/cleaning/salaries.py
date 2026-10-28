"""Salaries: "NPR 50,000 - 70,000 per month" -> min 50000, max 70000, NPR, month.

Text without numbers ("Negotiable", "As per company policy") gives no amounts; the
original wording is still stored in jobs.salary_text.
"""

import re
from typing import NamedTuple

from lakshya_backend.db.models import SalaryPeriod
from lakshya_scraper.cleaning.text import ascii_digits


class Salary(NamedTuple):
    min: int | None = None
    max: int | None = None
    currency: str | None = None
    period: SalaryPeriod | None = None


NO_SALARY = Salary()

# Checked in order: "indian rupees" must be seen as INR before the NPR rule sees "rupees"
_CURRENCIES = [
    ("USD", re.compile(r"\$|\busd\b|\bus\s*dollars?\b")),
    ("EUR", re.compile(r"€|\beur\b|\beuros?\b")),
    ("GBP", re.compile(r"£|\bgbp\b")),
    ("INR", re.compile(r"₹|\binr\b|indian rupees?")),
    ("NPR", re.compile(r"\bnpr\b|\bn?rs\b|रु|\brupees?\b")),
]
_PERIODS = [
    (SalaryPeriod.HOUR, re.compile(r"per\s*hour|/\s*h(ou)?r\b|hourly")),
    (SalaryPeriod.DAY, re.compile(r"per\s*day|/\s*day\b|daily")),
    (SalaryPeriod.WEEK, re.compile(r"per\s*week|/\s*w(ee)?k\b|weekly")),
    (SalaryPeriod.MONTH, re.compile(r"per\s*month|/\s*mo(nth)?\b|monthly|\bp\.?\s?m\b|a month")),
    (
        SalaryPeriod.YEAR,
        re.compile(r"per\s*(annum|year)|/\s*(year|yr|annum)\b|yearly|annual|\bp\.?\s?a\b|\blpa\b"),
    ),
]
_UNITS = {
    "k": 1_000, "thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
    "lacs": 100_000, "lpa": 100_000, "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000,
}  # fmt: skip

_NUMBER = r"(\d+(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|lpa|crores?|cr)?\b"
_CURRENCY_WORD = r"(?:npr|n?rs\.?|usd|\$|रु)?"
_RANGE = re.compile(_NUMBER + rf"\s*(?:-|–|—|to)\s*{_CURRENCY_WORD}\s*" + _NUMBER)
_SINGLE = re.compile(_NUMBER)
_UP_TO = re.compile(rf"(up\s*to|upto|max(imum)?|not more than|below)\W*{_CURRENCY_WORD}\W*$")
_AT_LEAST = re.compile(
    rf"(min(imum)?|from|starting|at least|above|more than)\W*{_CURRENCY_WORD}\W*$"
)

# Below this, a number with no currency written is probably not a salary ("13 months")
_MIN_UNMARKED_AMOUNT = 1_000


def parse_salary(text: str) -> Salary:
    text = ascii_digits(text.lower())
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 1,50,000 -> 150000

    if match := _RANGE.search(text):
        # "50 - 70k" means 50k to 70k: the lower number borrows the upper one's unit
        low = _amount(match.group(1), match.group(2) or match.group(4))
        high = _amount(match.group(3), match.group(4))
    elif match := _SINGLE.search(text):
        value = _amount(match.group(1), match.group(2))
        before = text[: match.start()]
        if _UP_TO.search(before):
            low, high = None, value
        elif _AT_LEAST.search(before):
            low, high = value, None
        else:
            low = high = value
    else:
        return NO_SALARY

    if low is not None and high is not None and low > high:
        return NO_SALARY  # e.g. a typo like "70,000 - 50,000": don't guess

    currency = next((code for code, pattern in _CURRENCIES if pattern.search(text)), None)
    if currency is None:
        # No currency written: every Phase 1 source is Nepali, so assume rupees,
        # but only for amounts that look like a salary
        if max(v for v in (low, high) if v is not None) < _MIN_UNMARKED_AMOUNT:
            return NO_SALARY
        currency = "NPR"

    period = next((period for period, pattern in _PERIODS if pattern.search(text)), None)
    return Salary(low, high, currency, period)


def _amount(number: str, unit: str | None) -> int:
    return round(float(number) * _UNITS.get(unit or "", 1))
