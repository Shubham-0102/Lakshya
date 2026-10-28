import pytest

from lakshya_scraper.scrapers.html import (
    block_text,
    country_name,
    experience_line,
    html_to_text,
    json_ld_job_posting,
    labelled_value,
    parse_html,
    text,
)


def test_text_tidies_whitespace_and_handles_missing_elements():
    soup = parse_html("<h1>\n  Senior   QA\n Engineer </h1><p></p>")

    assert text(soup.h1) == "Senior QA Engineer"
    assert text(soup.p) is None
    assert text(soup.find("h2")) is None


def test_block_text_keeps_one_line_per_block_and_drops_byte_order_marks():
    soup = parse_html(
        "<div>﻿Vacancy opening<p>Duties:</p><ul><li>Budgets</li><li>Reports</li></ul></div>"
    )

    assert block_text(soup.div) == "Vacancy opening\nDuties:\nBudgets\nReports"


def test_html_to_text_for_json_ld_descriptions():
    html = "<p><strong>About Leapfrog</strong></p><p>We build <em>products</em>.</p>"

    assert html_to_text(html) == "About Leapfrog\nWe build products."


def test_json_ld_job_posting_is_found_among_other_blocks():
    soup = parse_html(
        '<script type="application/ld+json">{"@type": "WebPage"}</script>'
        '<script type="application/ld+json">not json</script>'
        '<script type="application/ld+json">[{"@type": "JobPosting", "title": "QA"}]</script>'
    )

    assert json_ld_job_posting(soup) == {"@type": "JobPosting", "title": "QA"}
    assert json_ld_job_posting(parse_html("<p>none</p>")) is None


def test_labelled_value_reads_the_text_after_a_bold_label():
    # Markup as on F1Soft job pages
    soup = parse_html(
        '<p><span class="fw-bold">Location:</span> F1Soft Tower, Pulchowk, Lalitpur</p>'
        '<p><span class="fw-bold">Application Deadline:</span>\n 2026-10-30 </p>'
    )

    assert labelled_value(soup, "Location") == "F1Soft Tower, Pulchowk, Lalitpur"
    assert labelled_value(soup, "Application Deadline") == "2026-10-30"
    assert labelled_value(soup, "Salary") is None


def test_country_codes_become_names_the_cleaner_knows():
    assert country_name("NP") == "Nepal"
    assert country_name("in") == "India"
    assert country_name("ZZ") == "ZZ"
    assert country_name(None) is None


def test_experience_line_needs_the_word_experience_and_a_number():
    description = (
        "About us\nGreat experience for learners\n3+ years of experience with Python\nPerks"
    )

    assert experience_line(description) == "3+ years of experience with Python"
    assert experience_line("No numbers here, just experience") is None
    assert experience_line(None) is None


@pytest.mark.parametrize(
    "line",
    [
        # Real lines that mention experience and contain a number, but no amount of experience
        "Interested candidates who meet the required qualifications and experience are requested "
        "to apply through the portal by 2083/07/20",
        "Technical proposal (maximum 8 pages, excluding CVs and annexes): How the applicant's "
        "skills and experience fit",
    ],
)
def test_lines_without_an_amount_of_experience_are_ignored(line):
    assert experience_line(line) is None


@pytest.mark.parametrize(
    "line",
    [
        "1-2 of experience in full-stack development.",  # real F1Soft, "years" missing
        "Preferrable; 3+ years of experience as a QA Engineer",
        "6 months experience in sales",
    ],
)
def test_lines_with_an_amount_of_experience_are_found(line):
    assert experience_line(f"About the role\n{line}\nPerks") == line
