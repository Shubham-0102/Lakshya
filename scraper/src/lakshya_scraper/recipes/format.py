"""The recipe format: how to read one site's pages, written down as data.

A recipe is JSON stored in sources.recipe. It holds no code, so whatever writes it (a person,
or the AI in Phase 2) can only describe where things are on a page; our own interpreter in
scraper.py does the reading. The site's address is not part of a recipe: it comes from the
sources table, so a recipe can't send the scraper somewhere else.
"""

from typing import Annotated, Literal, Self

import soupsieve
from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator


def _valid_selector(selector: str) -> str:
    try:
        soupsieve.compile(selector)
    except soupsieve.SelectorSyntaxError as error:  # fail here, not halfway through a run
        raise ValueError(f"not a valid CSS selector: {selector!r}") from error
    return selector


Selector = Annotated[str, AfterValidator(_valid_selector)]


class Pick(BaseModel):
    """One way to read a value from a job page. Exactly one field is set."""

    model_config = ConfigDict(extra="forbid")

    css: Selector | None = None  # the first match's text, or its content="" attribute
    label: str | None = None  # the text after a label, e.g. "Location" in "Location: Lalitpur"
    json_ld: str | None = None  # a path in the JobPosting, e.g. "hiringOrganization.name"
    fixed: str | None = None  # always this value, e.g. the company on its own careers page

    @model_validator(mode="after")
    def exactly_one(self) -> Self:
        if sum(value is not None for value in self.model_dump().values()) != 1:
            raise ValueError("a Pick sets exactly one of css, label, json_ld, fixed")
        return self


Picks = list[Pick]  # tried in order: the first one that finds a value wins


class ListingRules(BaseModel):
    """How to read a listing page. Every selector inside `item` is relative to one posting."""

    model_config = ConfigDict(extra="forbid")

    item: Selector  # one posting on the page, e.g. "div.card-body"
    link: Selector  # the link to its job page, inside the item
    title: Selector | None = None  # shown on the listing: lets tenders be skipped unopened
    location: Selector | None = None
    next_page: Selector | None = None  # the link to the next listing page
    job_id: Literal["last_path_segment", "trailing_number"] = "last_path_segment"
    wait_for: Selector | None = None  # for pages that build their content with JavaScript


class JobRules(BaseModel):
    """How to read a job page."""

    model_config = ConfigDict(extra="forbid")

    title: Picks
    company: Picks
    location: Picks = []
    country: Picks = []  # added after the location: "Kathmandu" + "NP" -> "Kathmandu, Nepal"
    salary: Picks = []
    experience: Picks = []
    deadline: Picks = []
    posted: Picks = []
    description: Picks = []
    wait_for: Selector | None = None


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing: ListingRules
    job: JobRules
