import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def squash(text: str) -> str:
    """Trim, and collapse runs of whitespace (including newlines) into one space."""
    return re.sub(r"\s+", " ", text).strip()


def ascii_digits(text: str) -> str:
    """Nepali sites sometimes write numbers in Devanagari digits: २०८३ -> 2083."""
    return text.translate(_DEVANAGARI_DIGITS)
