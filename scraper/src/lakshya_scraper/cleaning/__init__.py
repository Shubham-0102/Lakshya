"""Cleaning: turn the text a scraper found (RawJob) into typed, normalized values (CleanJob).

Every function here is pure (text in, value out) and uses explicit rules, so each rule
can be tested and explained. Text that can't be parsed becomes None; the original stays
in job_sources.raw, and clean() logs it so the rules can grow.
"""

from lakshya_scraper.cleaning.clean import clean

__all__ = ["clean"]
