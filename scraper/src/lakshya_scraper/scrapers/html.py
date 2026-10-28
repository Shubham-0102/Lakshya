"""Small helpers the site scrapers share, built on BeautifulSoup."""

import json
import re

from bs4 import BeautifulSoup, Tag

from lakshya_scraper.cleaning.text import squash

_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6"]

# ISO codes used in structured data (JSON-LD, microdata) -> names the cleaner understands
_COUNTRY_NAMES = {
    "NP": "Nepal", "IN": "India", "US": "United States", "GB": "United Kingdom",
    "AU": "Australia", "CA": "Canada", "DE": "Germany", "AE": "UAE", "QA": "Qatar",
    "SG": "Singapore", "MY": "Malaysia", "BD": "Bangladesh", "JP": "Japan",
}  # fmt: skip


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def text(element: Tag | None) -> str | None:
    """An element's text on one line, or None if the element is missing or empty."""
    if element is None:
        return None
    return squash(element.get_text(" ").replace("﻿", "")) or None


def block_text(element: Tag | None) -> str | None:
    """An element's text with one line per paragraph, list item, heading, etc."""
    if element is None:
        return None
    for block in element.find_all(_BLOCK_TAGS):
        block.insert_before("\n")
    lines = (squash(line) for line in element.get_text().replace("﻿", "").splitlines())
    return "\n".join(line for line in lines if line) or None


def html_to_text(html: str) -> str | None:
    """Description HTML (e.g. from JSON-LD) -> plain text, one line per block."""
    return block_text(parse_html(html))


def json_ld_job_posting(soup: BeautifulSoup) -> dict | None:
    """The schema.org JobPosting embedded as JSON-LD, if the page has one."""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return item
    return None


def labelled_value(soup: BeautifulSoup | Tag, label: str) -> str | None:
    """The text after a label, e.g. <p><span class="fw-bold">Location:</span> Lalitpur</p>."""
    pattern = re.compile(rf"^\s*{re.escape(label)}\s*:?\s*$", re.IGNORECASE)
    label_node = soup.find(string=pattern)
    if label_node is None:
        return None
    container = label_node.parent.parent  # the <p> around the label's <span>
    value = squash(container.get_text(" ").replace(label_node, "", 1))
    return value.lstrip(":").strip() or None


# A line that mentions experience and states an amount of it: "3+ years", "6 months",
# "2-3 yrs", or a range right before "experience" ("1-2 of experience")
_EXPERIENCE_LINE = re.compile(
    r"(?=.*\bexperience\b)"
    r"(?=.*(\d+\s*\+?\s*((-|–|—|to)\s*\d+\s*\+?\s*)?(years?|yrs?|months?)\b"
    r"|\d+\s*(-|–|—|to)\s*\d+\s+(of\s+)?experience))",
    re.IGNORECASE,
)


def experience_line(description: str | None) -> str | None:
    """The first line of a description that states how much experience is needed, e.g.
    "2-3 years of prior work experience in BA roles." (the cleaner parses it)."""
    lines = (description or "").splitlines()
    return next((line for line in lines if _EXPERIENCE_LINE.search(line)), None)


def country_name(code: str | None) -> str | None:
    if not code:
        return None
    return _COUNTRY_NAMES.get(code.upper(), code)
