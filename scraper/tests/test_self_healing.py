"""Self-healing with a fake model, on real saved pages made to look like a site redesign.

`redesign` renames what a recipe's selectors point at, so the old recipe breaks the same way
it would on the day a site changes its layout. The jobs themselves stay the same.
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from lakshya_backend.db.models import ComplianceStatus, HealthStatus, Job, Source, SourceType
from lakshya_scraper import pipeline
from lakshya_scraper.fetching import FetchError, SiteAskedToStop
from lakshya_scraper.llm import Llm, LlmError, Reply
from lakshya_scraper.pipeline import run_with_healing, scrape
from lakshya_scraper.recipes import ListingRules, Pick, Recipe, RecipeScraper
from lakshya_scraper.scrapers import ListingItem, ListingPage, Scraper

FIXTURES = Path(__file__).parent / "fixtures" / "f1soft"
URL = "https://career.f1soft.com/jobs"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


OLD_RECIPE = Recipe.model_validate_json(read("recipe.json"))
OLD_RECIPE.listing.next_page = None  # the saved listing's page 2 isn't on the fake site


def redesign_listing(html: str) -> str:
    return html.replace("features-job", "vacancy-card").replace("location-div", "place")


def redesign_job(html: str) -> str:
    return html.replace("job-content", "posting-body").replace("fs-4", "headline")


NEW_LISTING = OLD_RECIPE.listing.model_copy(
    update={"item": "div.vacancy-card", "location": ".place .small"}
)
NEW_JOB = OLD_RECIPE.job.model_copy(
    update={"title": [Pick(css="h2.headline")], "description": [Pick(css="div.posting-body")]}
)
LISTING = read("listing.html")
JOB = read("job.html")
TITLES = {
    item.url: item.title
    for item in RecipeScraper("f1soft", URL, OLD_RECIPE).parse_listing(LISTING, URL).items
}


class Site:
    """The fake website: the listing at URL, and at each job's address the saved job page
    with that job's title on it."""

    def __init__(self, listing: str = LISTING, job: str = JOB, job_error: Exception | None = None):
        self.listing, self.job, self.job_error = listing, job, job_error
        self.requests: list[str] = []

    def fetch(self, url: str, wait_for: str | None = None, settle_ms: int = 0) -> str:
        self.requests.append(url)
        if url == URL:
            return self.listing
        if self.job_error:
            raise self.job_error
        return self.job.replace("Business Analyst", TITLES[url], 1)

    def fetch_text(self, url: str) -> str:
        return self.fetch(url)


class FakeModel:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, model: str, prompt: str, schema: dict) -> Reply:
        self.calls += 1
        return Reply(self.answers.pop(0).model_dump_json(), 100, 10)


@pytest.fixture
def source(db_session):
    example = Source(
        slug="healing-example",
        name="F1Soft Careers",
        base_url=URL,
        type=SourceType.CAREER_PAGE,
        compliance_status=ComplianceStatus.APPROVED,
        enabled=True,
        recipe=OLD_RECIPE.model_dump(mode="json", exclude_none=True),
    )
    db_session.add(example)
    db_session.commit()
    return example


@pytest.fixture
def use_model(monkeypatch):
    def install(model: FakeModel) -> FakeModel:
        monkeypatch.setattr(pipeline, "get_llm", lambda: Llm(model, ["fake"], attempts=1))
        return model

    return install


def run(db_session, source, site, recipe: Recipe = OLD_RECIPE):
    return run_with_healing(db_session, source, RecipeScraper(source.slug, URL, recipe), site)


def saved_jobs(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(Job))


def saved_recipe(source) -> Recipe:
    return Recipe.model_validate(source.recipe)


# A working site needs no AI


def test_a_healthy_run_makes_no_ai_call(db_session, source, use_model):
    model = use_model(FakeModel())

    result = run(db_session, source, Site())

    assert (result.new, result.healing, model.calls) == (3, None, 0)


# The redesigns


def test_a_full_redesign_is_repaired_and_the_jobs_are_saved(db_session, source, use_model):
    use_model(FakeModel(NEW_LISTING, NEW_JOB))
    site = Site(redesign_listing(LISTING), redesign_job(JOB))

    result = run(db_session, source, site)

    assert result.healing == "healed"
    assert (result.problem, result.new) == (None, 3)
    assert saved_jobs(db_session) == 3
    assert saved_recipe(source).listing == NEW_LISTING
    assert saved_recipe(source).job == NEW_JOB
    assert source.recipe_learned_at is not None


def test_a_repaired_source_is_healthy_with_no_failures_counted(db_session, source, use_model):
    use_model(FakeModel(NEW_LISTING, NEW_JOB))

    run(db_session, source, Site(redesign_listing(LISTING), redesign_job(JOB)))

    assert (source.health_status, source.failure_count) == (HealthStatus.HEALTHY, 0)


def test_the_repaired_recipe_works_on_the_next_run_with_no_ai(db_session, source, use_model):
    use_model(FakeModel(NEW_LISTING, NEW_JOB))
    site = Site(redesign_listing(LISTING), redesign_job(JOB))
    run(db_session, source, site)
    model = use_model(FakeModel())

    result = run(db_session, source, site, saved_recipe(source))

    assert (result.seen_again, result.problem, model.calls) == (3, None, 0)


def test_when_only_the_listing_changed_only_the_listing_is_relearned(db_session, source, use_model):
    model = use_model(FakeModel(NEW_LISTING))

    result = run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert result.healing == "healed"
    assert model.calls == 1
    assert saved_recipe(source).job == OLD_RECIPE.job


def test_when_only_the_job_page_changed_only_the_job_rules_are_relearned(
    db_session, source, use_model
):
    model = use_model(FakeModel(NEW_JOB))

    result = run(db_session, source, Site(LISTING, redesign_job(JOB)))

    assert result.healing == "healed"
    assert model.calls == 1
    assert saved_recipe(source).listing == OLD_RECIPE.listing


def test_job_pages_that_lose_their_description_trigger_a_repair(db_session, source, use_model):
    """Nothing crashes when an optional field goes missing, so it needs its own check."""
    no_description = OLD_RECIPE.model_copy(deep=True)
    no_description.job.description = [Pick(css=".no-such-body")]
    model = use_model(FakeModel(OLD_RECIPE.job))

    result = run(db_session, source, Site(), no_description)

    assert result.healing == "healed"
    assert model.calls == 1


# When repair isn't possible, the old recipe stays and the failure is visible


def test_ai_rules_that_fail_keep_the_old_recipe(db_session, source, use_model):
    useless = ListingRules(item="div.still-wrong", link="a", title="a")
    use_model(FakeModel(useless, useless))

    result = run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert result.healing.startswith("failed")
    assert saved_recipe(source) == OLD_RECIPE
    assert source.health_status == HealthStatus.DEGRADED
    assert source.failure_count == 1


def test_when_the_ai_is_unavailable_the_run_still_finishes(db_session, source, monkeypatch):
    def no_model():
        raise LlmError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(pipeline, "get_llm", no_model)

    result = run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert "GEMINI_API_KEY" in result.healing
    assert result.problem
    assert saved_recipe(source) == OLD_RECIPE


def test_a_recipe_that_passes_on_one_page_but_fails_a_real_run_is_undone(
    db_session, source, use_model, monkeypatch
):
    """Only the first job page reads; the rest fail, so the new recipe isn't really better."""
    use_model(FakeModel(NEW_LISTING))
    real_scrape = scrape
    runs = []

    def second_run_fails(*args, **kwargs):
        result = real_scrape(*args, **kwargs)
        runs.append(result)
        if len(runs) == 2:
            result.problem = "3 of 3 job pages failed"
        return result

    monkeypatch.setattr(pipeline, "scrape", second_run_fails)

    result = run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert "didn't work" in result.healing
    assert saved_recipe(source) == OLD_RECIPE


def test_a_site_with_no_openings_is_not_mistaken_for_a_fixable_recipe(
    db_session, source, use_model
):
    empty = "<html><body><p>No current openings</p></body></html>"
    useless = ListingRules(item="div.nothing", link="a", title="a")
    use_model(FakeModel(useless, useless))

    result = run(db_session, source, Site(empty, JOB))

    assert result.healing.startswith("failed")
    assert saved_recipe(source) == OLD_RECIPE


# When not to spend AI calls


def test_job_pages_that_are_down_cost_no_ai_call(db_session, source, use_model):
    """The recipe still reads the listing and the job page: the layout isn't the problem."""
    model = use_model(FakeModel())

    class DownOnFirstPass(Site):
        def fetch(self, url, wait_for=None, settle_ms=0):
            if url != URL and not settle_ms:  # healing's own check reads them fine
                self.requests.append(url)
                raise FetchError("server error")
            return super().fetch(url, wait_for, settle_ms)

    result = run(db_session, source, DownOnFirstPass())

    assert result.healing.startswith("failed: the recipe still reads the site")
    assert model.calls == 0


def test_a_site_that_says_stop_is_left_alone(db_session, source, use_model):
    model = use_model(FakeModel())

    class AsksToStop(Site):
        def fetch(self, url, wait_for=None, settle_ms=0):
            raise SiteAskedToStop("career.f1soft.com answered 429")

    result = run(db_session, source, AsksToStop())

    assert (result.healing, model.calls) == (None, 0)


def test_a_failing_source_waits_for_a_person(db_session, source, use_model):
    model = use_model(FakeModel())
    source.failure_count = 2  # this run makes three in a row

    result = run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert (source.health_status, result.healing, model.calls) == (HealthStatus.FAILING, None, 0)


def test_a_broken_source_spends_at_most_one_round_of_ai_calls_per_run(
    db_session, source, use_model
):
    useless = ListingRules(item="div.still-wrong", link="a", title="a")
    model = use_model(FakeModel(useless, useless, useless, useless))

    run(db_session, source, Site(redesign_listing(LISTING), JOB))

    assert model.calls == 2  # one attempt, one retry with the failure explained


def test_hand_written_scrapers_never_heal_themselves(db_session, source, use_model):
    model = use_model(FakeModel())

    class HandWritten(Scraper):
        slug = source.slug

        def first_listing_url(self) -> str:
            return URL

        def parse_listing(self, html: str, url: str) -> ListingPage:
            return ListingPage([])

        def parse_detail(self, html: str, item: ListingItem):
            raise NotImplementedError

    result = run_with_healing(db_session, source, HandWritten(), Site())

    assert result.problem
    assert (result.healing, model.calls) == (None, 0)
