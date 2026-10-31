"""Experience: "2+ years" -> (2, None), "1-2 years" -> (1, 2), "Fresher" -> (0, 0)."""

import re
from decimal import Decimal

from lakshya_scraper.cleaning.text import ascii_digits, number_words_to_digits

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
_MAX_YEARS = 20  # anything bigger is a misread (usually the employer's age), not a requirement
# Longer than this is a sentence, not a field like "2+ years". A sentence can mention years that
# aren't a requirement ("It is two years of supervised programme"), so there they only count
# with the word "experience" near them or a word like "minimum" before them.
_LONG_TEXT = 60
_EXPERIENCE_FOLLOWS = re.compile(r"[^.;]*\bexperience\b")
_EXPERIENCE_BEFORE = re.compile(r"\bexperience\b[^.;]{0,25}$")  # "Strong experience (7+ years)"
_AT_LEAST = re.compile(r"(min(imum)?( of)?|at\s*least)\s*$")
# The employer's history, not a requirement: "a Barcelona-based company with over 15 years of
# experience", "With more than 35 years of experience in Nepal, the charity supports..."
_ABOUT_THE_EMPLOYER = re.compile(
    r"\b(compan(y|ies)|organi[sz]ation|firm|agency|group|provider)\b[^.;]{0,40}\bwith\b"
    r"|^\s*with (more than|over|nearly|almost)\b"
)

Years = Decimal | None


def parse_experience(text: str) -> tuple[Years, Years]:
    text = number_words_to_digits(ascii_digits(text.lower()))
    fresher = bool(_FRESHER.search(text))

    # The requirement stated first is the main one: in "5+ years of experience with 2-3 years
    # in management" the answer is 5+, so take the earliest match, not the first pattern
    matches = [
        match
        for pattern in (_RANGE, _RANGE_WITHOUT_UNIT, _SINGLE)
        for match in pattern.finditer(text)
        if _is_requirement(text, match)
    ]
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


def _is_requirement(text: str, match: re.Match) -> bool:
    before = text[: match.start()]
    if _ABOUT_THE_EMPLOYER.search(re.split(r"[.;]\s", before)[-1]):
        return False
    return (
        len(text) <= _LONG_TEXT
        or match.re is _RANGE_WITHOUT_UNIT  # has "experience" in the match itself
        or bool(_EXPERIENCE_FOLLOWS.match(text, match.end()))
        or bool(_EXPERIENCE_BEFORE.search(before))
        or bool(_AT_LEAST.search(before))
    )


def _years(number: str, unit: str) -> Decimal:
    value = Decimal(number)
    if unit.startswith("month"):
        value /= 12
    return value.quantize(Decimal("0.1"))
