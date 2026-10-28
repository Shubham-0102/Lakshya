"""robots.txt parsing, using the real files saved during the source review (2026-10-28)."""

import pytest

from lakshya_scraper.fetching.robots import ALLOW_ALL, disallow_all, parse_robots

UA = "Lakshya/0.1 (+https://github.com/Shubham-0102/Lakshya)"

KUMARIJOB = """\
# Main website configuration
User-agent: *
# Allow specific pages
Allow: /sitemap.xml
Allow: /jobseeker$
Allow: /search$

# Block admin and system paths
Disallow: /admin/
Disallow: /api/
Disallow: /kumari-job/
Disallow: /index.php

# Block dynamic pages
Disallow: /jobseeker*
Disallow: /jobseeker?

# Block asset directories
Disallow: /public/**/*.zip
Disallow: /v2/training/*

Host: www.kumarijob.com
Sitemap: https://www.kumarijob.com/sitemap.xml
"""

GURZU = """\
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /*?*
Disallow: /*&*
Disallow: /services/rails-maintenance/
Allow: /img/
"""

F1SOFT_MAIN = """\
User-agent: *
Disallow: /

Allow: /$
Allow: /about
Allow: /business/esewa
"""

KHALTI_BLOG = "User-Agent: *\nDisallow: /\n"

LEAPFROG_CAREER = (
    "User-Agent: *\n\nDisallow: /v/\n\nSitemap: https://career.lftechnology.com/sitemap.xml\n"
)

MEROJOB = """\
User-agent: *
Content-Signal: ai-train=no, search=yes, ai-input=yes
Disallow:

Sitemap: https://merojob.com/sitemap.xml
"""


@pytest.mark.parametrize(
    ("robots", "url", "allowed"),
    [
        # kumarijob: wildcards, and a tie between Allow and Disallow of the same length
        (KUMARIJOB, "https://www.kumarijob.com/capital-max-securities-ltd/77736-associate", True),
        (KUMARIJOB, "https://www.kumarijob.com/jobseeker", True),  # Allow /jobseeker$ wins tie
        (KUMARIJOB, "https://www.kumarijob.com/jobseeker/profile", False),  # /jobseeker*
        (KUMARIJOB, "https://www.kumarijob.com/jobseeker?page=2", False),
        (KUMARIJOB, "https://www.kumarijob.com/api/jobs", False),
        (KUMARIJOB, "https://www.kumarijob.com/public/files/2026/cv.zip", False),  # /**/*.zip
        (KUMARIJOB, "https://www.kumarijob.com/public/files/logo.png", True),
        # Gurzu: /*?* blocks anything with a query string; longest match beats "Allow: /"
        (GURZU, "https://gurzu.com/services/web-development/", True),
        (GURZU, "https://gurzu.com/careers?ref=home", False),
        (GURZU, "https://gurzu.com/admin/login", False),
        # F1Soft main site: everything blocked except listed pages; "$" anchors the homepage
        (F1SOFT_MAIN, "https://f1soft.com/", True),
        (F1SOFT_MAIN, "https://f1soft.com/about", True),
        (F1SOFT_MAIN, "https://f1soft.com/business/esewa", True),
        (F1SOFT_MAIN, "https://f1soft.com/careers", False),
        # Khalti blog: nothing allowed
        (KHALTI_BLOG, "https://blog.khalti.com/careers/", False),
        # Leapfrog careers host: only /v/ is blocked
        (LEAPFROG_CAREER, "https://career.lftechnology.com/o/senior-full-stack-developer-3", True),
        (LEAPFROG_CAREER, "https://career.lftechnology.com/v/123", False),
        # Merojob: unknown lines (Content-Signal) are ignored; empty Disallow allows all
        (MEROJOB, "https://merojob.com/seo-intern-33", True),
    ],
)
def test_real_robots_files(robots, url, allowed):
    assert parse_robots(robots, UA).allows(url) is allowed


def test_group_for_our_user_agent_beats_the_star_group():
    robots = "User-agent: *\nAllow: /\n\nUser-agent: Lakshya\nDisallow: /\n"

    assert not parse_robots(robots, UA).allows("https://example.com/jobs")


def test_user_agent_match_ignores_case():
    robots = "User-agent: LAKSHYA\nDisallow: /private\n"

    assert not parse_robots(robots, UA).allows("https://example.com/private/x")


def test_several_user_agents_can_share_one_group():
    robots = "User-agent: googlebot\nUser-agent: lakshya\nDisallow: /search\n"

    assert not parse_robots(robots, UA).allows("https://example.com/search")


def test_crawl_delay_is_read():
    robots = "User-agent: *\nCrawl-delay: 10\nDisallow:\n"

    assert parse_robots(robots, UA).crawl_delay == 10


def test_rules_before_any_user_agent_are_ignored():
    assert parse_robots("Disallow: /\n", UA).allows("https://example.com/jobs")


def test_empty_file_allows_everything():
    assert parse_robots("", UA).allows("https://example.com/anything")


def test_allow_all_and_disallow_all():
    assert ALLOW_ALL.allows("https://example.com/x")
    assert not disallow_all().allows("https://example.com/x")
