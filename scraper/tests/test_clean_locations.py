import pytest

from lakshya_scraper.cleaning.locations import clean_location, is_known_place


@pytest.mark.parametrize(
    ("text", "name", "is_remote", "outside_nepal"),
    [
        # Real, from the sources
        ("F1Soft Tower, Pulchowk, Lalitpur District, Nepal", "Lalitpur", False, False),
        ("Pulchowk, lalitpur", "Lalitpur", False, False),
        ("Kathmandu, Nepal", "Kathmandu", False, False),
        ("Pune, India", "Pune, India", False, True),
        (
            "NFWLHA Central Office, Kathmandu (Frequent travel to program district)",
            "Kathmandu",
            False,
            False,
        ),
        # Aliases, areas and districts
        ("KTM", "Kathmandu", False, False),
        ("Kathmandu Valley", "Kathmandu", False, False),
        ("New Baneshwor, Kathmandu", "Kathmandu", False, False),
        ("Patan", "Lalitpur", False, False),
        ("Kaski", "Pokhara", False, False),
        ("Bhairahawa", "Siddharthanagar", False, False),
        ("Nepal", "Nepal", False, False),
        ("All over Nepal", "Nepal", False, False),
        # Remote
        ("Remote", None, True, False),
        ("Work from home", None, True, False),
        ("Kathmandu (Hybrid/Remote)", "Kathmandu", True, False),
        ("Remote (USA)", "Remote (USA)", True, True),
    ],
)
def test_clean_location(text, name, is_remote, outside_nepal):
    location = clean_location(text)

    assert (location.name, location.is_remote, location.outside_nepal) == (
        name,
        is_remote,
        outside_nepal,
    )
    assert location.recognized


def test_unknown_place_is_kept_as_text_and_flagged():
    location = clean_location("  Province   1 ")

    assert location.name == "Province 1"
    assert not location.recognized


@pytest.mark.parametrize("text", ["Kathmandu", "Lalitpur District", "KTM", "Nepal"])
def test_is_known_place(text):
    assert is_known_place(text)


@pytest.mark.parametrize("text", ["eXtensoData", "Engineering", "Aquaculture Grants Support"])
def test_is_not_a_place(text):
    assert not is_known_place(text)
