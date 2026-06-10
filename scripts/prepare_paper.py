"""make-paper helper: resolve assets, stage samples, collect Wiki sources,
compute the German dateline, and emit a JSON manifest for the subagent."""
from __future__ import annotations

import re
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


def parse_authors(md_text: str) -> tuple[list[str], str]:
    """Return (author_names, institution) parsed from an authors.md body."""
    names: list[str] = []
    institution = ""
    for raw in md_text.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            names.append(line[2:].strip())
        elif line.lower().startswith("institution:"):
            institution = line.split(":", 1)[1].strip()
    if not institution:
        for raw in md_text.splitlines():
            m = re.match(r"^(.*?),\s*[A-Za-zÄÖÜäöü]+\s+\d{4}\s*$", raw.strip())
            if m:
                institution = m.group(1).strip()
                break
    return names, institution
