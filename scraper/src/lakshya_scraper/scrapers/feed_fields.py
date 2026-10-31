"""Small helpers the feed scrapers share: turn a feed's typed fields into the page-like text
a RawJob holds, so one cleaner handles every source."""

from datetime import UTC, datetime

# The words feeds use for a pay period -> the word the salary cleaner reads
_PERIODS = {
    "hour": "hour", "hourly": "hour",
    "day": "day", "daily": "day",
    "week": "week", "weekly": "week",
    "month": "month", "monthly": "month",
    "year": "year", "yearly": "year", "annual": "year", "annually": "year",
}  # fmt: skip


def remote_location(place: str | None) -> str:
    """Every job in a remote feed is remote; a place next to that limits who can take it.
    "Boston" -> "Remote - Boston", which cleaning drops. Nothing -> "Remote"."""
    place = (place or "").strip()
    if not place or "remote" in place.lower():
        return place or "Remote"
    return f"Remote - {place}"


def salary_text(low: float | None, high: float | None, currency: str | None, period: str | None):
    """Feed salary fields -> text the cleaner reads, e.g. "USD 3000 - 6000 per month".
    Some feeds use 0 to mean "not given"."""
    if not currency or not (low or high):
        return None
    amount = f"{low} - {high}" if low and high and low != high else str(low or high)
    word = _PERIODS.get((period or "").lower())
    return f"{currency} {amount} per {word}" if word else f"{currency} {amount}"


def day_from_epoch(seconds: int | None) -> str | None:
    """Unix seconds -> "2026-10-31"."""
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, UTC).date().isoformat()
