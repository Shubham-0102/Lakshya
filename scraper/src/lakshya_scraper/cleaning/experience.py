"""Experience: "2+ years" -> (2, None), "1-2 years" -> (1, 2), "Fresher" -> (0, 0)."""

import re
from decimal import Decimal

from lakshya_scraper.cleaning.text import ascii_digits

_NUMBER = r"(\d+(?:\.\d+)?)"
_UNIT = r"(years?|yrs?|months?)"
_RANGE = re.compile(rf"{_NUMBER}\s*(?:-|–|—|to)\s*{_NUMBER}\s*\+?\s*{_UNIT}")
_SINGLE = re.compile(rf"{_NUMBER}\s*\+?\s*{_UNIT}")
# "1-2 of experience" (the unit left out, as in a real F1Soft posting): read as years
_RANGE_WITHOUT_UNIT = re.compile(rf"{_NUMBER}\s*(?:-|–|—|to)\s*{_NUMBER}\s+(?:of\s+)?experience")
_AT_MOST = re.compile(r"(up\s*to|upto|max(imum)?( of)?|less than|not more than|below)\s*$")
_FRESHER = re.compile(
    r"\bfreshers?\b|\bfresh graduates?\b|\bno (prior |previous )?experience\b|\bentry[- ]level\b"
    r"|\bexperience (is )?not required\b"
)
_MAX_YEARS = 50  # anything bigger is a misread, not a requirement

Years = Decimal | None


def parse_experience(text: str) -> tuple[Years, Years]:
    text = ascii_digits(text.lower())
    fresher = bool(_FRESHER.search(text))

    # The requirement stated first is the main one: in "5+ years of experience with 2-3 years
    # in management" the answer is 5+, so take the earliest match, not the first pattern
    matches = [m for m in (p.search(text) for p in (_RANGE, _RANGE_WITHOUT_UNIT, _SINGLE)) if m]
    if not matches:
        return (Decimal(0), Decimal(0)) if fresher else (None, None)
    match = min(matches, key=lambda m: m.start())

    if match.re is _RANGE:
        low, high = _years(match.group(1), match.group(3)), _years(match.group(2), match.group(3))
    elif match.re is _RANGE_WITHOUT_UNIT:
        low, high = _years(match.group(1), "years"), _years(match.group(2), "years")
    else:
        value = _years(match.group(1), match.group(2))
        # "Minimum 5 years", "5+ years" and plain "5 years" all mean at least 5
        low, high = (None, value) if _AT_MOST.search(text[: match.start()]) else (value, None)

    if any(v is not None and v > _MAX_YEARS for v in (low, high)):
        return None, None
    if fresher:
        # "Fresher or 1-2 years": freshers are welcome, so the minimum is 0
        low = Decimal(0)
    return low, high


def _years(number: str, unit: str) -> Decimal:
    value = Decimal(number)
    if unit.startswith("month"):
        value /= 12
    return value.quantize(Decimal("0.1"))
