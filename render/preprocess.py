"""Pure Markdown transforms for make-paper Subsystem B. No external processes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_HEADING_NUM = re.compile(r"^(#{1,6})\s+\d+(?:\.\d+)*\.?\s+(.*\S)\s*$")


def strip_heading_numbers(md: str) -> str:
    """Remove a leading section number (e.g. '2.' or '2.3') from ATX headings."""
    out = []
    for line in md.splitlines():
        m = _HEADING_NUM.match(line)
        out.append(f"{m.group(1)} {m.group(2)}" if m else line)
    return "\n".join(out)


_H1 = re.compile(r"^#\s+(.*\S)\s*$")


def extract_title(md: str) -> tuple[str | None, str]:
    """Return (title, body_without_title). Title = first level-1 ATX heading."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = _H1.match(line)
        if m:
            del lines[i]
            return m.group(1), "\n".join(lines)
    return None, md


_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_ABSTRACT_TITLES = {"abstract", "zusammenfassung", "kurzfassung"}


def extract_abstract(md: str) -> tuple[str | None, str]:
    """Pull out a leading Abstract/Zusammenfassung/Kurzfassung section.

    Returns (abstract_text, body_without_that_section). The abstract spans from
    just after its heading to the next heading of the same or higher level.
    """
    lines = md.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().lower() in _ABSTRACT_TITLES:
            start, level = i, len(m.group(1))
            break
    if start is None:
        return None, md
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    abstract = "\n".join(lines[start + 1:end]).strip()
    body = "\n".join(lines[:start] + lines[end:]).strip("\n")
    return abstract, body
