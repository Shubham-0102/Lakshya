"""Make a page small and safe to show the AI: it needs the page's structure, not its text.

Real career pages run to 100,000 characters, mostly scripts and styles. What's left here is
the skeleton a selector can be written for. Long text is cut, which saves tokens and keeps
most of what a posting says about people away from a free-tier model; emails and phone
numbers are removed outright. Recipes are always checked against the full page afterwards.
"""

import json
import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from lakshya_scraper.scrapers.html import json_ld_job_posting, parse_html

MAX_PAGE_CHARS = 40_000
_MAX_TEXT = 80  # a job title fits; a paragraph doesn't need to
_MAX_JSON_TEXT = 120
_KEEP_PER_RUN = 3  # of many alike siblings (job cards, list items), keep these and the last

_REMOVED_TAGS = [
    "script", "style", "noscript", "svg", "iframe", "template", "canvas", "footer", "head",
]  # fmt: skip
_NEXT_PAGE = re.compile(r"next|older|»|›", re.IGNORECASE)
_KEPT_ATTRIBUTES = {
    "class", "id", "href", "rel", "itemprop", "itemtype", "itemscope", "content", "datetime",
    "name", "role",
}  # fmt: skip

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# International, Nepali mobile and Nepali landline; dates must not match
_PHONE = re.compile(r"\+\d[\d\s()-]{7,}\d|\b9[678]\d{8}\b|\b0\d{1,2}-\d{6,7}\b")


def shrink_page(html: str, collapse_runs: bool = True) -> str:
    """`collapse_runs`: for listings, where 20 job cards teach no more than 3. Not for job
    pages, where a run of alike table rows holds a different field in each row."""
    soup = parse_html(html)
    posting = json_ld_job_posting(soup)  # read before scripts go; JSON-LD is often all a site has
    for tag in soup(_REMOVED_TAGS):
        tag.decompose()
    for menu in soup("nav"):  # menus link to jobs too, which misleads selectors
        if not menu.find("a", rel="next") and not menu.find("a", string=_NEXT_PAGE):
            menu.decompose()  # but pagination often sits in a <nav>, and must stay
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        comment.extract()

    body = soup.body or soup
    for tag in body.find_all(True):
        _trim_attributes(tag)
    for node in body.find_all(string=True):
        _shorten_text(node)
    if collapse_runs:
        _collapse_runs(body)

    page = re.sub(r"\s*\n\s*", "\n", body.decode())
    if posting:
        page += f"\n<!-- JSON-LD JobPosting on this page: {_scrubbed_json(posting)} -->"
    return page[:MAX_PAGE_CHARS]


def _trim_attributes(tag: Tag) -> None:
    for name in list(tag.attrs):
        if name not in _KEPT_ATTRIBUTES:
            del tag.attrs[name]
    href = tag.attrs.get("href", "")
    if isinstance(href, str) and href.startswith(("mailto:", "tel:")):
        del tag.attrs["href"]
    content = tag.attrs.get("content")
    if isinstance(content, str):
        tag.attrs["content"] = _scrub(content)[:_MAX_TEXT]


def _shorten_text(node: NavigableString) -> None:
    text = _scrub(str(node))
    if len(text) > _MAX_TEXT:
        text = f"{text[:_MAX_TEXT]}…"
    node.replace_with(text)


def _scrub(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


def _collapse_runs(parent: Tag) -> None:
    """Keep the first few of a run of alike siblings, and the last: "next" is often there."""
    children = [child for child in parent.find_all(True, recursive=False)]
    groups: dict[tuple, list[Tag]] = {}
    for child in children:
        groups.setdefault((child.name, tuple(child.get("class") or ())), []).append(child)
    for group in groups.values():
        if len(group) > _KEEP_PER_RUN + 1:
            for extra in group[_KEEP_PER_RUN:-1]:
                extra.decompose()
    for child in parent.find_all(True, recursive=False):
        _collapse_runs(child)


def _scrubbed_json(value: object) -> str:
    return json.dumps(_shorten_json(value), ensure_ascii=False)


def _shorten_json(value: object) -> object:
    if isinstance(value, str):
        text = BeautifulSoup(value, "lxml").get_text(" ") if "<" in value else value
        return _scrub(text)[:_MAX_JSON_TEXT]
    if isinstance(value, list):
        return [_shorten_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _shorten_json(item) for key, item in value.items()}
    return value
