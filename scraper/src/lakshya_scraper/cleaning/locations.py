"""Locations: map the many ways a place is written to one city, and detect remote work.

"F1Soft Tower, Pulchowk, Lalitpur District, Nepal" -> Lalitpur
"KTM" / "Kathmandu Valley" / "New Baneshwor"      -> Kathmandu
"""

import re
from typing import NamedTuple

from lakshya_scraper.cleaning.text import squash

# City we store -> lowercased ways of writing it. Areas inside a city or district map to
# that district's main city; a district maps to its city only when the city is obvious.
_CITY_ALIASES = {
    "Kathmandu": [
        "kathmandu", "ktm", "kathmandu valley", "kathmandu metropolitan city",
        "baneshwor", "new baneshwor", "old baneshwor", "thamel", "lazimpat", "maharajgunj",
        "baluwatar", "naxal", "durbarmarg", "kamaladi", "putalisadak", "dillibazar",
        "koteshwor", "tinkune", "sinamangal", "gyaneshwor", "thapathali", "tripureshwor",
        "teku", "kalanki", "balaju", "chabahil", "boudha", "jorpati", "budhanilkantha",
        "tokha", "kirtipur", "babarmahal", "bhatbhateni", "hattisar", "kamalpokhari",
        "battisputali", "gaushala", "sundhara", "new road", "bagbazar", "minbhawan",
        "shankhamul", "samakhusi", "basundhara", "chakrapath", "sitapaila", "swayambhu",
    ],
    "Lalitpur": [
        "lalitpur", "patan", "pulchowk", "jawalakhel", "sanepa", "kupondole", "lagankhel",
        "jhamsikhel", "ekantakuna", "satdobato", "imadol", "kumaripati", "manbhawan",
        "bakhundole", "gwarko", "hattiban", "dhobighat", "thasikhel",
    ],
    "Bhaktapur": ["bhaktapur", "thimi", "madhyapur thimi", "suryabinayak", "lokanthali"],
    "Pokhara": ["pokhara", "kaski", "lakeside"],
    "Bharatpur": ["bharatpur", "chitwan", "narayangarh", "narayanghat"],
    "Biratnagar": ["biratnagar", "morang"],
    "Butwal": ["butwal"],
    "Siddharthanagar": ["siddharthanagar", "bhairahawa"],
    "Birgunj": ["birgunj", "parsa"],
    "Dharan": ["dharan"],
    "Itahari": ["itahari"],
    "Hetauda": ["hetauda", "makwanpur"],
    "Nepalgunj": ["nepalgunj", "banke"],
    "Dhangadhi": ["dhangadhi", "kailali"],
    "Janakpur": ["janakpur", "janakpurdham", "dhanusha"],
    "Damak": ["damak"],
    "Banepa": ["banepa"],
    "Dhulikhel": ["dhulikhel"],
}  # fmt: skip

# Places that are clearly outside Nepal (we keep Nepal and remote jobs only)
_FOREIGN_PLACES = [
    "india", "pune", "bangalore", "bengaluru", "delhi", "new delhi", "mumbai", "noida",
    "gurgaon", "gurugram", "hyderabad", "chennai", "kolkata", "usa", "united states",
    "uk", "united kingdom", "london", "australia", "sydney", "canada", "germany", "japan",
    "qatar", "doha", "uae", "dubai", "saudi arabia", "malaysia", "singapore", "bangladesh",
    "dhaka", "pakistan", "sri lanka", "philippines", "netherlands", "denmark",
]  # fmt: skip

_ALIAS_TO_CITY = {alias: city for city, aliases in _CITY_ALIASES.items() for alias in aliases}


def _whole_words(phrases: list[str]) -> re.Pattern:
    # Longest first, so "new baneshwor" wins over "baneshwor"
    alternatives = "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True))
    return re.compile(rf"\b({alternatives})\b")


_CITY = _whole_words(list(_ALIAS_TO_CITY))
_FOREIGN = _whole_words(_FOREIGN_PLACES)
_NEPAL = re.compile(r"\bnepal\b")
_REMOTE = re.compile(r"\b(remote|work from home|wfh|telecommut\w*|telework\w*|worldwide)\b")
# Placeholders from sites' posting forms that name no place, e.g. "Other - Specify"
_PLACEHOLDER = re.compile(r"^(other( ?- ?specify)?|n/?a|not specified|-+)$")
_DISTRICT_WORDS = re.compile(
    r"\b(sub-?\s?metropolitan city|metropolitan city|municipality|district)\b"
)


class Location(NamedTuple):
    name: str | None  # a known city, "Nepal", or the cleaned original text
    is_remote: bool
    outside_nepal: bool
    recognized: bool  # False if no rule matched; clean() logs these so the lists can grow


def clean_location(text: str) -> Location:
    text = squash(text)
    lowered = text.lower()
    if _PLACEHOLDER.match(lowered):
        return Location(None, False, False, True)
    is_remote = bool(_REMOTE.search(lowered))

    # The first known place wins: in "Pulchowk, Lalitpur District" that's Pulchowk -> Lalitpur
    if match := _CITY.search(lowered):
        return Location(_ALIAS_TO_CITY[match.group(1)], is_remote, False, True)
    if _NEPAL.search(lowered):
        # Keep a place we don't know yet: "Dhading, Nepal" -> "Dhading" (logged so the
        # alias list can grow). Phrases like "All over Nepal" become just "Nepal".
        parts = [
            part.strip()
            for part in text.split(",")
            if part.strip().lower() != "nepal"
            and not _PLACEHOLDER.match(part.strip().lower())
            and _REMOTE.sub("", part.lower()).strip(" ()")
        ]
        if parts and not any(_NEPAL.search(part.lower()) for part in parts):
            return Location(", ".join(parts), is_remote, False, False)
        return Location("Nepal", is_remote, False, True)

    outside_nepal = bool(_FOREIGN.search(lowered))
    # "Remote" on its own isn't a place to store
    rest = squash(_REMOTE.sub(" ", lowered).strip(" ,;/|-()"))
    return Location(text if rest else None, is_remote, outside_nepal, outside_nepal or is_remote)


def is_known_place(text: str) -> bool:
    """True if the whole text is a place, e.g. "Kathmandu" or "Lalitpur District"."""
    key = squash(_DISTRICT_WORDS.sub(" ", text.lower()))
    return key in _ALIAS_TO_CITY or key == "nepal"
