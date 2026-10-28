import pytest

from lakshya_scraper.cleaning.companies import clean_company_name, normalize_company


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("F1Soft International Pvt. Ltd.", "f1soft international"),
        ("F1Soft International", "f1soft international"),  # same key: the two merge
        ("Leapfrog Technology Inc.", "leapfrog technology"),
        ("FoneNXT", "fonenxt"),
        ("ABC & Sons P. Ltd", "abc and sons"),
        ("Nabil Bank Limited", "nabil bank"),
        ("Himalayan Bank Ltd.", "himalayan bank"),
        # Real, jobsnepal
        (
            "National Federation of Women Living with HIV & AIDS",
            "national federation of women living with hiv and aids",
        ),
        ("Ltd.", "ltd"),  # never strips a name down to nothing
    ],
)
def test_normalize_company(name, expected):
    assert normalize_company(name) == expected


def test_display_name_keeps_the_original_spelling():
    assert (
        clean_company_name("  F1Soft   International Pvt. Ltd. ")
        == "F1Soft International Pvt. Ltd."
    )
