import re

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def squash(text: str) -> str:
    """Trim, and collapse runs of whitespace (including newlines) into one space."""
    return re.sub(r"\s+", " ", text).strip()


def ascii_digits(text: str) -> str:
    """Nepali sites sometimes write numbers in Devanagari digits: २०८३ -> 2083."""
    return text.translate(_DEVANAGARI_DIGITS)


_MOJIBAKE = re.compile("[\xc2-\xf4][\x80-\xbf]+")


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 that was read as Latin-1 on the way to us: "Ã©" -> "é". Only the broken
    parts are touched, so the rest of the text can be any language."""

    def repair(match: re.Match) -> str:
        try:
            return match.group().encode("latin-1").decode("utf-8")
        except UnicodeDecodeError:
            return match.group()

    return _MOJIBAKE.sub(repair, text)


_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}  # fmt: skip
NUMBER_WORD = "|".join(_NUMBER_WORDS)


def number_words_to_digits(text: str) -> str:
    """ "At least three years" -> "At least 3 years" (one to ten)."""
    return re.sub(
        rf"\b({NUMBER_WORD})\b", lambda m: _NUMBER_WORDS[m.group(1).lower()], text, flags=re.I
    )
