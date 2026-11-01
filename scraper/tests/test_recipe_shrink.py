"""shrink_page: what the AI is shown. This is also the privacy boundary for a free-tier model."""

from pathlib import Path

import pytest

from lakshya_scraper.recipes import Recipe
from lakshya_scraper.recipes.shrink import MAX_PAGE_CHARS, shrink_page
from lakshya_scraper.scrapers.html import parse_html

FIXTURES = Path(__file__).parent / "fixtures"
SITES = ["f1soft", "jobsnepal", "leapfrog"]


def page(body: str) -> str:
    return f"<html><head><title>Jobs</title><style>b {{}}</style></head><body>{body}</body></html>"


def test_scripts_styles_menus_and_footers_are_removed():
    shrunk = shrink_page(
        page(
            "<script>var x = 1;</script><style>p {}</style><nav><a href='/jobs/1'>Menu</a></nav>"
            "<main><h1>Backend Engineer</h1></main><footer>Copyright</footer><!-- a comment -->"
        )
    )

    assert "Backend Engineer" in shrunk
    for gone in ("var x", "p {}", "Menu", "Copyright", "a comment", "<title>"):
        assert gone not in shrunk


def test_attributes_a_selector_can_use_are_kept_and_others_dropped():
    shrunk = shrink_page(
        page(
            '<div id="x" class="card" itemprop="title" data-track="abc" style="color:red" '
            'onclick="go()"><a href="/jobs/1" rel="next" target="_blank">Job</a></div>'
        )
    )

    for kept in ('id="x"', 'class="card"', 'itemprop="title"', 'href="/jobs/1"', 'rel="next"'):
        assert kept in shrunk
    for gone in ("data-track", "style=", "onclick", "target="):
        assert gone not in shrunk


@pytest.mark.parametrize(
    "secret",
    [
        "hr@example.com",
        "first.last+jobs@mail.example.com.np",
        "+977 1 5971871",
        "+977-9801234567",
        "9841234567",
        "01-5970015",
    ],
)
def test_emails_and_phone_numbers_never_reach_the_ai(secret):
    assert secret not in shrink_page(page(f"<p>Send your CV to {secret} today</p>"))


def test_contact_links_lose_their_address():
    shrunk = shrink_page(
        page('<a href="mailto:hr@example.com">Mail</a><a href="tel:+9779841234567">Call</a>')
    )

    assert "hr@example.com" not in shrunk
    assert "9841234567" not in shrunk


def test_contact_details_in_meta_content_and_json_ld_are_removed_too():
    shrunk = shrink_page(
        page(
            '<meta itemprop="email" content="hr@example.com"><script type="application/ld+json">'
            '{"@type": "JobPosting", "title": "Engineer", "description": "Mail hr@example.com"}'
            "</script>"
        )
    )

    assert "hr@example.com" not in shrunk


@pytest.mark.parametrize("value", ["2026-10-30", "Oct 30, 2026", "NPR 50,000 - 70,000"])
def test_dates_and_pay_are_not_mistaken_for_phone_numbers(value):
    assert value in shrink_page(page(f"<p>{value}</p>"))


def test_long_text_is_cut_but_a_title_is_not():
    shrunk = shrink_page(page(f"<h1>Backend Engineer</h1><p>{'word ' * 100}</p>"))

    assert "Backend Engineer" in shrunk
    assert "word " * 30 not in shrunk


def test_a_long_run_of_alike_elements_keeps_a_few_and_the_last():
    cards = "".join(f'<div class="card">Job {n}</div>' for n in range(20))

    shrunk = shrink_page(page(f"<main>{cards}</main>"))

    assert shrunk.count('class="card"') == 4
    assert "Job 0" in shrunk
    assert "Job 19" in shrunk


def test_the_next_page_link_survives_being_last_in_a_long_pagination():
    links = "".join(f'<li><a href="?page={n}">{n}</a></li>' for n in range(1, 9))
    last = '<li><a rel="next" href="?page=2">Next</a></li>'

    assert 'rel="next"' in shrink_page(page(f"<ul>{links}{last}</ul>"))


@pytest.mark.parametrize(
    "pagination",
    [
        '<nav><a href="?page=2" rel="next">Next &raquo;</a></nav>',  # real, F1Soft and JobsNepal
        '<nav class="pager"><a href="?page=2">Next</a></nav>',
        '<nav><a href="?page=2">»</a></nav>',
    ],
)
def test_pagination_inside_a_nav_stays_visible(pagination):
    assert 'href="?page=2"' in shrink_page(page(f"<main><h1>Jobs</h1></main>{pagination}"))


def test_job_pages_keep_every_row_of_a_table_of_fields():
    rows = "".join(f"<tr><td>Field {n}</td><td>Value {n}</td></tr>" for n in range(10))

    shrunk = shrink_page(page(f"<table>{rows}</table>"), collapse_runs=False)

    assert "Value 5" in shrunk


def test_json_ld_job_posting_is_shown_and_shortened():
    shrunk = shrink_page(
        page(
            '<script type="application/ld+json">{"@type": "JobPosting", "title": "Engineer", '
            f'"hiringOrganization": {{"name": "Acme"}}, "description": "<p>{"long " * 200}</p>"}}'
            "</script><h1>Engineer</h1>"
        )
    )

    assert '"hiringOrganization": {"name": "Acme"}' in shrunk
    assert "long " * 40 not in shrunk


def test_size_is_capped():
    cards = "".join(f'<section id="s{n}"><h2>Heading {n}</h2></section>' for n in range(5000))

    assert len(shrink_page(page(cards))) <= MAX_PAGE_CHARS


@pytest.mark.parametrize("site", SITES)
def test_what_the_ai_sees_is_enough_to_write_the_real_recipe(site):
    """The hand-written recipes' selectors must still find things on the shrunken pages."""
    recipe = Recipe.model_validate_json((FIXTURES / site / "recipe.json").read_text("utf-8"))
    html = (FIXTURES / site / "listing.html").read_text("utf-8")

    soup = parse_html(shrink_page(html))
    postings = soup.select(recipe.listing.item)

    assert postings
    assert postings[0].select_one(recipe.listing.link)
    assert postings[0].select_one(recipe.listing.title)


@pytest.mark.parametrize("site", SITES)
def test_real_pages_get_much_smaller_or_stay_small(site):
    html = (FIXTURES / site / "job.html").read_text("utf-8")

    assert len(shrink_page(html)) <= len(html) + 1500  # JSON-LD is added back as a comment
