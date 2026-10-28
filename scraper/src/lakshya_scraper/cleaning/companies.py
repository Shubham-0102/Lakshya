"""Company names: one normalized key per employer, so the same company merges across sites.

"F1Soft International Pvt. Ltd." and "F1Soft International" -> "f1soft international"
"""

import re

from lakshya_scraper.cleaning.text import squash

# Legal-form words removed from the end of a name
_LEGAL_SUFFIXES = {
    "pvt", "private", "p", "ltd", "limited", "inc", "incorporated", "llc", "llp", "co",
    "corp", "corporation", "plc",
}  # fmt: skip


def clean_company_name(name: str) -> str:
    """The display name: as written, with whitespace tidied."""
    return squash(name)


def normalize_company(name: str) -> str:
    words = re.sub(r"[^0-9a-zऀ-ॿ]+", " ", name.lower().replace("&", " and ")).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words) or squash(name).lower()
