from decimal import Decimal

import pytest

from lakshya_scraper.cleaning.experience import parse_experience


def years(value):
    return None if value is None else Decimal(str(value))


@pytest.mark.parametrize(
    ("text", "expected_min", "expected_max"),
    [
        # Real, from the sources
        ("2-3 years of prior work experience in BA roles.", 2, 3),  # F1Soft
        (
            "Minimum of 5 years of experience in finance or accounting, preferably in a "
            "non-profit organization.",  # jobsnepal
            5,
            None,
        ),
        (
            "5+ years of experience with 2-3 years in people management, engineering "
            "management, staff management, or a similar leadership role",  # Leapfrog
            5,
            None,
        ),
        # Common forms
        ("1-2 of experience in full-stack development.", 1, 2),  # real F1Soft: "years" missing
        ("2+ years", 2, None),
        ("1 to 2 years", 1, 2),
        ("3 yrs", 3, None),
        ("1.5 years", 1.5, None),
        ("6 months", 0.5, None),
        ("6-12 months", 0.5, 1),
        ("At least 4 years", 4, None),
        ("Up to 2 years", None, 2),
        ("Less than 1 year", None, 1),
        # Freshers
        ("Fresher", 0, 0),
        ("Fresh Graduate", 0, 0),  # real, jobsnepal
        ("Freshers can also apply", 0, 0),
        ("No experience required", 0, 0),
        ("Fresher or 1-2 years", 0, 2),
        # Nothing usable
        ("Relevant experience preferred", None, None),
        ("200 years", None, None),
    ],
)
def test_parse_experience(text, expected_min, expected_max):
    assert parse_experience(text) == (years(expected_min), years(expected_max))
