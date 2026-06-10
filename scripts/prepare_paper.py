"""make-paper helper: resolve assets, stage samples, collect Wiki sources,
compute the German dateline, and emit a JSON manifest for the subagent."""
from __future__ import annotations

from datetime import date

GERMAN_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def german_month(month: int) -> str:
    """Return the German month name for a 1-based month number."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    return GERMAN_MONTHS[month - 1]


def german_dateline(institution: str, today: date) -> str:
    """e.g. ('RWTH Aachen', 2026-06-10) -> 'RWTH Aachen, Juni 2026'."""
    return f"{institution}, {german_month(today.month)} {today.year}"
