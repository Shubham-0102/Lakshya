"""Job titles: remove noise that sites add, fix ALL-CAPS, and spot notices that aren't jobs."""

import re

from lakshya_scraper.cleaning.locations import is_known_place
from lakshya_scraper.cleaning.text import squash

# "Urgent Hiring: Backend Developer" -> "Backend Developer". A separator is required,
# so a real title such as "Hiring Manager" is left alone.
_NOISE_PREFIX = re.compile(
    r"^(urgent(ly)?(\s+(hiring|requirement|required|vacancy))?|hiring|now hiring"
    r"|we\s*'?re\s+hiring|vacancy|job opening|wanted)\s*[:|\-–—]\s*",
    re.IGNORECASE,
)
# "Accountant (2 Positions)" -> "Accountant"
_POSITION_COUNT = re.compile(
    r"\s*[(\[]\s*\d+\s*(positions?|posts?|nos?\.?|vacanc(y|ies)|openings?|seats?)\s*[)\]]",
    re.IGNORECASE,
)
# A trailing "- Kathmandu" or "(Kathmandu)"; only removed if it really is a place
_TRAILING_PART = re.compile(r"\s*(?:[-–—,|]\s*([^-–—,|()]+)|\(([^()]+)\))\s*$")

# Tenders and notices that portals list alongside jobs
_NOT_A_JOB = re.compile(
    r"call for (bids?|proposals?|quotations?|tenders?)|invitation for (bids?|quotations?)"
    r"|bid notice|sealed quotation|expression of interest|\beoi\b|terms of reference|\btor\b"
    r"|request for (proposals?|quotations?)|\brfp\b|\brfq\b|\btenders?\b|talent pool"
    r"|बोलपत्र|दरभाउपत्र",  # Nepali: bid, quotation
    re.IGNORECASE,
)

# Kept upper-case when fixing an ALL-CAPS title. MEAL and WASH are common in NGO jobs
# (Monitoring, Evaluation, Accountability and Learning; Water, Sanitation and Hygiene).
ACRONYMS = {
    "AI", "API", "AWS", "BA", "BI", "CEO", "CFO", "COO", "CRM", "CTO", "DBA", "EOI", "ERP",
    "GIS", "HR", "ICT", "INGO", "IT", "MEAL", "MIS", "ML", "NGO", "PR", "QA", "QC", "SEO",
    "SQL", "UI", "UN", "UX", "VP", "WASH",
}  # fmt: skip
_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to"}


def is_job_posting(title: str) -> bool:
    return not _NOT_A_JOB.search(title)


def clean_title(title: str) -> str:
    cleaned = _NOISE_PREFIX.sub("", squash(title))
    cleaned = _POSITION_COUNT.sub("", cleaned)
    match = _TRAILING_PART.search(cleaned)
    if match and is_known_place(match.group(1) or match.group(2)):
        cleaned = cleaned[: match.start()]
    cleaned = _fix_all_caps(squash(cleaned))
    return cleaned or squash(title)


def normalize_title(title: str) -> str:
    """Lowercase words only, for comparing titles: "Full-Stack Dev." -> "full stack dev"."""
    text = title.lower().replace("&", " and ")
    return squash(re.sub(r"[^0-9a-zऀ-ॿ]+", " ", text))  # keeps Devanagari


def _fix_all_caps(title: str) -> str:
    """ "SENIOR QA ENGINEER" -> "Senior QA Engineer". Mixed-case titles are left as written."""
    if sum(c.isalpha() for c in title) < 4 or title != title.upper():
        return title

    def fix_word(match: re.Match) -> str:
        word = match.group(0)
        if word in ACRONYMS:
            return word
        if match.start() > 0 and word.lower() in _SMALL_WORDS:
            return word.lower()
        return word.capitalize()

    return re.sub(r"[A-Za-z]+", fix_word, title)
