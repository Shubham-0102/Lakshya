import json

import pytest

from lakshya_scraper import __main__ as cli
from lakshya_scraper.job_format import RawJob
from lakshya_scraper.pipeline import Preview, RunResult
from lakshya_scraper.scrapers import ListingItem

ITEM = ListingItem("42", "https://jobs.example.com/jobs/42")
RAW = RawJob(
    source_slug="example",
    external_id="42",
    url=ITEM.url,
    title="Backend Engineer",
    company="Acme",
    description="x" * 1000,
)


@pytest.fixture(autouse=True)
def example_scraper(monkeypatch):
    monkeypatch.setitem(cli.SCRAPERS, "example", object)


def test_unknown_source_is_rejected(capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "nope"])

    assert "invalid choice" in capsys.readouterr().err


def test_dry_run_prints_raw_and_clean_jobs_and_saves_nothing(monkeypatch, capsys):
    from lakshya_scraper.cleaning import clean

    monkeypatch.setattr(cli, "preview_source", lambda slug, limit: [Preview(ITEM, RAW, clean(RAW))])
    monkeypatch.setattr(cli, "run_source", lambda *a, **k: pytest.fail("dry run must not save"))

    assert cli.main(["run", "example", "--dry-run"]) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["raw"]["title"] == "Backend Engineer"
    assert len(printed["raw"]["description"]) == 300  # shortened for reading
    assert printed["clean"]["normalized_title"] == "backend engineer"


def test_real_run_exits_non_zero_when_the_source_has_a_problem(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "run_source", lambda slug, limit: RunResult(slug, problem="no jobs found")
    )

    assert cli.main(["run", "example"]) == 1
    assert json.loads(capsys.readouterr().out)["problem"] == "no jobs found"
