import pytest

from lakshya_backend.db.models import SalaryPeriod
from lakshya_scraper.cleaning.salaries import NO_SALARY, Salary, parse_salary

MONTH, YEAR, HOUR = SalaryPeriod.MONTH, SalaryPeriod.YEAR, SalaryPeriod.HOUR


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Ranges
        ("NPR 50,000 - 70,000 per month", Salary(50_000, 70_000, "NPR", MONTH)),
        ("Rs. 50,000 to Rs. 70,000", Salary(50_000, 70_000, "NPR", None)),
        ("NRs. 30,000 – 40,000 monthly", Salary(30_000, 40_000, "NPR", MONTH)),
        ("50-70k monthly", Salary(50_000, 70_000, "NPR", MONTH)),  # unit borrowed from upper
        ("1.5 - 2 lakh", Salary(150_000, 200_000, "NPR", None)),
        ("USD 25 - 35 per hour", Salary(25, 35, "USD", HOUR)),
        # Single amounts and units
        ("Rs. 50K", Salary(50_000, 50_000, "NPR", None)),
        ("Rs 1,50,000", Salary(150_000, 150_000, "NPR", None)),  # Nepali digit grouping
        ("1.5 lakh per annum", Salary(150_000, 150_000, "NPR", YEAR)),
        ("5 LPA", Salary(500_000, 500_000, "NPR", YEAR)),
        ("$1,200/month", Salary(1_200, 1_200, "USD", MONTH)),
        ("INR 30,000 per month", Salary(30_000, 30_000, "INR", MONTH)),
        ("रु ४०,०००", Salary(40_000, 40_000, "NPR", None)),  # Devanagari digits
        ("Rs. 45,000 p.m.", Salary(45_000, 45_000, "NPR", MONTH)),
        # Only one end given
        ("Up to Rs 70,000", Salary(None, 70_000, "NPR", None)),
        ("Minimum NPR 40,000", Salary(40_000, None, "NPR", None)),
    ],
)
def test_parse_salary(text, expected):
    assert parse_salary(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Negotiable",
        "As per company policy",
        "Competitive and attractive",
        "13 months salary",  # a small number with no currency is not a salary
        "70,000 - 50,000",  # inverted range: don't guess which number is wrong
    ],
)
def test_text_without_a_usable_amount_gives_no_salary(text):
    assert parse_salary(text) == NO_SALARY
