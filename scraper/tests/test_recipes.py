"""Recipes on the saved pages of real sites.

The hand-written scrapers are the baseline: a recipe must read the same pages to the same
result. That proves the interpreter works, and later gives an honest accuracy number for
recipes the AI writes.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from lakshya_backend.db.models import ComplianceStatus, Job, Source, SourceType
from lakshya_scraper.cleaning import clean
from lakshya_scraper.pipeline import scrape
from lakshya_scraper.recipes import JobRules, ListingRules, Pick, Recipe, RecipeScraper
from lakshya_scraper.scrapers import ListingItem
from lakshya_scraper.scrapers.f1soft import F1SoftScraper
from lakshya_scraper.scrapers.jobsnepal import JobsNepalScraper
from lakshya_scraper.scrapers.leapfrog import LeapfrogScraper

FIXTURES = Path(__file__).parent / "fixtures"

SITES = [
    pytest.param(F1SoftScraper, "f1soft", "https://career.f1soft.com/jobs", id="f1soft"),
    pytest.param(JobsNepalScraper, "jobsnepal", "https://www.jobsnepal.com/jobs", id="jobsnepal"),
    pytest.param(
        LeapfrogScraper, "leapfrog", "https://www.lftechnology.com/careers", id="leapfrog"
    ),
]


def read(site: str, name: str) -> str:
    return (FIXTURES / site / name).read_text(encoding="utf-8")


def recipe_for(site: str) -> Recipe:
    return Recipe.model_validate_json(read(site, "recipe.json"))


def scrapers(hand_written, site: str, url: str) -> tuple:
    return hand_written(), RecipeScraper(site, url, recipe_for(site))


def job_item(hand, site: str, url: str) -> ListingItem:
    """The posting the saved job page belongs to, as the hand-written tests name it."""
    return {
        "f1soft": ListingItem(
            "business-analyst-fonenxt", "https://career.f1soft.com/jobs/business-analyst-fonenxt"
        ),
        "jobsnepal": ListingItem(
            "144747", "https://www.jobsnepal.com/adminfinance-coordinator-144747"
        ),
        "leapfrog": ListingItem(
            "engineering-staff-manager",
            "https://career.lftechnology.com/o/engineering-staff-manager",
        ),
    }[site]


def raw_fields(raw) -> dict:
    return raw.model_dump(exclude={"scraped_at"})


def clean_fields(raw) -> dict:
    return clean(raw).model_dump()


@pytest.mark.parametrize(("hand_written", "site", "url"), SITES)
def test_recipe_reads_the_listing_like_the_hand_written_scraper(hand_written, site, url):
    hand, recipe = scrapers(hand_written, site, url)
    html = read(site, "listing.html")

    expected, actual = hand.parse_listing(html, url), recipe.parse_listing(html, url)

    assert actual.items == expected.items
    assert actual.next_url == expected.next_url
    assert expected.items  # the comparison means nothing on an empty page


@pytest.mark.parametrize(("hand_written", "site", "url"), SITES)
def test_recipe_reads_a_job_page_like_the_hand_written_scraper(hand_written, site, url):
    hand, recipe = scrapers(hand_written, site, url)
    html = read(site, "job.html")
    item = job_item(hand, site, url)

    assert raw_fields(recipe.parse_detail(html, item)) == raw_fields(hand.parse_detail(html, item))


@pytest.mark.parametrize(("hand_written", "site", "url"), SITES)
def test_recipe_job_cleans_to_the_same_job(hand_written, site, url):
    hand, recipe = scrapers(hand_written, site, url)
    html = read(site, "job.html")
    item = job_item(hand, site, url)

    assert clean_fields(recipe.parse_detail(html, item)) == clean_fields(
        hand.parse_detail(html, item)
    )


@pytest.mark.parametrize(("hand_written", "site", "url"), SITES)
def test_saved_recipes_survive_a_trip_through_json(hand_written, site, url):
    recipe = recipe_for(site)

    assert Recipe.model_validate(recipe.model_dump()) == recipe


def test_recipe_waits_for_pages_built_with_javascript():
    _, recipe = scrapers(LeapfrogScraper, "leapfrog", "https://www.lftechnology.com/careers")

    assert recipe.listing_wait_for == LeapfrogScraper.listing_wait_for.replace('"', "'")


# The rules of the format


def minimal(**job_fields) -> Recipe:
    rules = {
        "title": [Pick(css="h1")],
        "company": [Pick(fixed="Acme")],
        "description": [Pick(css="body")],
    } | job_fields
    return Recipe(listing=ListingRules(item="li", link="a"), job=JobRules(**rules))


def scraper_with(recipe: Recipe) -> RecipeScraper:
    return RecipeScraper("example", "https://jobs.example.com/", recipe)


ITEM = ListingItem("1", "https://jobs.example.com/jobs/1", title="From the listing")


@pytest.mark.parametrize("fields", [{}, {"css": "h1", "label": "Title"}])
def test_a_pick_sets_exactly_one_way_of_reading(fields):
    with pytest.raises(ValidationError):
        Pick(**fields)


@pytest.mark.parametrize("field", ["title", "company", "description"])
def test_a_recipe_must_say_how_to_read_the_fields_a_job_needs(field):
    rules = {"title": [Pick(css="h1")], "company": [Pick(css="h2")], "description": [Pick(css="p")]}

    with pytest.raises(ValidationError):  # left out, as a real model did with description
        JobRules(**{name: picks for name, picks in rules.items() if name != field})
    with pytest.raises(ValidationError):  # or given with no way of reading it
        JobRules(**(rules | {field: []}))


def test_the_ai_is_told_these_fields_are_required():
    assert {"title", "company", "description"} <= set(JobRules.model_json_schema()["required"])


def test_a_bad_selector_is_rejected_when_the_recipe_loads():
    with pytest.raises(ValidationError):
        Pick(css="div[")

    with pytest.raises(ValidationError):
        ListingRules(item="li", link="a[")


def test_unknown_fields_are_rejected_so_a_typo_fails_loudly():
    with pytest.raises(ValidationError):
        Pick(selector="h1")


def test_a_recipe_cannot_carry_its_own_address():
    data = recipe_for("f1soft").model_dump()
    data["listing"]["url"] = "https://somewhere-else.example.com"

    with pytest.raises(ValidationError):
        Recipe.model_validate(data)


def test_first_pick_with_a_value_wins():
    recipe = minimal(deadline=[Pick(css=".missing"), Pick(css=".empty"), Pick(css=".date")])
    html = '<h1>Engineer</h1><p class="empty"> </p><p class="date">Nov 30</p>'

    assert scraper_with(recipe).parse_detail(html, ITEM).deadline == "Nov 30"


def test_css_reads_a_content_attribute_before_text():
    recipe = minimal(posted=[Pick(css="meta[itemprop=datePosted]")])
    html = '<h1>Engineer</h1><meta itemprop="datePosted" content="2026-10-28">'

    assert scraper_with(recipe).parse_detail(html, ITEM).posted == "2026-10-28"


def test_json_path_takes_the_first_of_a_list():
    recipe = minimal(location=[Pick(json_ld="jobLocation.address.addressLocality")])
    html = """<h1>Engineer</h1><script type="application/ld+json">
    {"@type": "JobPosting", "jobLocation": [
        {"address": {"addressLocality": "Kathmandu"}}, {"address": {"addressLocality": "Pune"}}
    ]}</script>"""

    assert scraper_with(recipe).parse_detail(html, ITEM).location == "Kathmandu"


def test_json_path_to_nothing_is_no_value():
    recipe = minimal(salary=[Pick(json_ld="baseSalary.value.minValue")])

    assert scraper_with(recipe).parse_detail("<h1>Engineer</h1>", ITEM).salary is None


def test_json_path_to_a_number_reads_as_text():
    recipe = minimal(salary=[Pick(json_ld="baseSalary.value.minValue")])
    html = """<h1>Engineer</h1><script type="application/ld+json">
    {"@type": "JobPosting", "baseSalary": {"value": {"minValue": 50000}}}</script>"""

    assert scraper_with(recipe).parse_detail(html, ITEM).salary == "50000"


def test_country_codes_become_names_after_the_location():
    recipe = minimal(location=[Pick(fixed="Kathmandu")], country=[Pick(fixed="NP")])

    assert scraper_with(recipe).parse_detail("<h1>x</h1>", ITEM).location == "Kathmandu, Nepal"


def test_title_falls_back_to_the_listing():
    raw = scraper_with(minimal(title=[Pick(css=".missing")])).parse_detail("<p>x</p>", ITEM)

    assert raw.title == "From the listing"


def test_experience_comes_from_the_description_when_no_field_gives_numbers():
    recipe = minimal(experience=[Pick(fixed="See details")], description=[Pick(css="#d")])
    html = "<h1>x</h1><div id=d><p>You will build APIs.</p><p>3+ years of experience.</p></div>"

    assert scraper_with(recipe).parse_detail(html, ITEM).experience == "3+ years of experience."


def test_a_missing_required_field_fails_instead_of_saving_a_broken_job():
    recipe = minimal(company=[Pick(css=".missing")])

    with pytest.raises(ValidationError):
        scraper_with(recipe).parse_detail("<h1>Engineer</h1>", ITEM)


def test_listing_skips_postings_without_a_usable_link():
    html = (
        '<ul><li><a href="/jobs/1">One</a></li><li><span>No link</span></li><li><a>x</a></li></ul>'
    )

    page = scraper_with(minimal()).parse_listing(html, "https://jobs.example.com/jobs")

    assert [item.external_id for item in page.items] == ["1"]
    assert page.items[0].url == "https://jobs.example.com/jobs/1"
    assert page.next_url is None


def test_trailing_number_ids_skip_links_without_one():
    recipe = minimal()
    recipe.listing.job_id = "trailing_number"
    html = (
        '<ul><li><a href="/backend-engineer-144747">a</a></li><li><a href="/about">b</a></li></ul>'
    )

    page = scraper_with(recipe).parse_listing(html, "https://jobs.example.com/")

    assert [item.external_id for item in page.items] == ["144747"]


def test_next_page_is_followed_only_when_it_has_an_address():
    recipe = minimal()
    recipe.listing.next_page = "a.next"
    html = '<ul><li><a href="/jobs/1">One</a></li></ul><a class="next">Next</a>'

    assert scraper_with(recipe).parse_listing(html, "https://jobs.example.com/").next_url is None


# The pipeline can't tell a recipe from a hand-written scraper


class SavedSite:
    """Serves the saved listing for the first URL and the saved job page for every other."""

    def __init__(self, site: str, listing_url: str):
        self.site = site
        self.listing_url = listing_url
        self.fetched: list[str] = []

    def fetch(self, url: str, wait_for: str | None = None) -> str:
        self.fetched.append(url)
        return read(self.site, "listing.html" if url == self.listing_url else "job.html")


def test_a_recipe_runs_through_the_real_pipeline(db_session):
    url = "https://career.f1soft.com/jobs"
    source = Source(
        slug="f1soft-recipe",
        name="F1Soft",
        base_url="https://career.f1soft.com",
        type=SourceType.CAREER_PAGE,
        compliance_status=ComplianceStatus.APPROVED,
        enabled=True,
    )
    db_session.add(source)
    db_session.flush()
    # The saved listing links to a page 2 that the fake site doesn't have: stop after one page
    recipe = recipe_for("f1soft")
    recipe.listing.next_page = None
    fetcher = SavedSite("f1soft", url)

    result = scrape(db_session, source, RecipeScraper(source.slug, url, recipe), fetcher)

    assert (result.found, result.new, result.failed, result.problem) == (3, 3, 0, None)
    assert db_session.query(Job).count() == 3
