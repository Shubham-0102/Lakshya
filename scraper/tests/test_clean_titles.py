import pytest

from lakshya_scraper.cleaning.titles import clean_title, is_job_posting, normalize_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Real titles from the sources: nothing to remove
        ("Admin/Finance Coordinator", "Admin/Finance Coordinator"),
        ("Staff Manager (Engineering)", "Staff Manager (Engineering)"),
        ("Interns - Aquaculture Grants Support", "Interns - Aquaculture Grants Support"),
        ("Senior Full-Stack Developer", "Senior Full-Stack Developer"),
        ("Finance and Admin officer", "Finance and Admin officer"),  # mixed case: left as written
        # Noise that sites add
        ("Urgent Hiring: Backend Developer", "Backend Developer"),
        ("Vacancy - Accountant", "Accountant"),
        ("Hiring Manager", "Hiring Manager"),  # no separator: "Hiring" is part of the title
        ("Accountant (2 Positions)", "Accountant"),
        ("Accountant [3 posts]", "Accountant"),
        ("Backend Developer - Kathmandu", "Backend Developer"),
        ("Backend Developer (Lalitpur)", "Backend Developer"),
        ("Data Engineer - eXtensoData", "Data Engineer - eXtensoData"),  # not a place: kept
        ("  Senior   Software\nEngineer ", "Senior Software Engineer"),
        # ALL CAPS
        ("SENIOR QA ENGINEER", "Senior QA Engineer"),
        ("HEAD OF IT AND HR", "Head of IT and HR"),
        ("UI/UX DESIGNER", "UI/UX Designer"),
        ("MEAL OFFICER", "MEAL Officer"),
        ("Urgent Hiring: SENIOR QA ENGINEER (2 Positions) - Kathmandu", "Senior QA Engineer"),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


@pytest.mark.parametrize(
    "title",
    [
        "CALL FOR EXPRESSION OF INTEREST (EOI)",  # real, jobsnepal
        "Expression of Interest (EOI) for Consultancy Service for Baseline Study",  # real
        "बोलपत्र आह्वान (Call for Bid)",  # real, jobsnepal ("bid invitation")
        "Join our Talent Pool",  # real, Leapfrog
        "Terms of Reference (ToR) for External Auditing Services",
        "Request for Proposal: Website Redesign",
        "Sealed Quotation Notice",
        "Tender Notice for Office Supplies",
    ],
)
def test_tenders_and_notices_are_not_job_postings(title):
    assert not is_job_posting(title)


@pytest.mark.parametrize(
    "title", ["Data Manager", "Project Officer", "Bartender", "Director", "Mentor", "Doctor"]
)
def test_real_jobs_are_not_mistaken_for_notices(title):
    """Word boundaries: "tender" in Bartender and "tor" in Director must not match."""
    assert is_job_posting(title)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior QA Engineer", "senior qa engineer"),
        ("Full-Stack Dev.", "full stack dev"),
        ("R&D Engineer", "r and d engineer"),
        ("Admin/Finance Coordinator", "admin finance coordinator"),
        ("लेखापाल (Accountant)", "लेखापाल accountant"),  # Devanagari is kept
    ],
)
def test_normalize_title(title, expected):
    assert normalize_title(title) == expected
