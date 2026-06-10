import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))

import preprocess as pre


def test_strip_heading_numbers_removes_leading_numbers():
    md = "# Titel\n## 1. Einleitung\n### 2.3 Unterabschnitt\n## Fazit\nText 1. bleibt.\n"
    out = pre.strip_heading_numbers(md)
    assert "## Einleitung" in out
    assert "### Unterabschnitt" in out
    assert "## Fazit" in out
    assert "# Titel" in out
    # body text containing a number must be untouched
    assert "Text 1. bleibt." in out


def test_extract_title_pulls_first_h1_and_removes_it():
    md = "# Mein Titel\n\n## Einleitung\nText\n"
    title, body = pre.extract_title(md)
    assert title == "Mein Titel"
    assert "# Mein Titel" not in body
    assert "## Einleitung" in body


def test_extract_title_ignores_h2_and_returns_none():
    md = "## Einleitung\nText\n"
    title, body = pre.extract_title(md)
    assert title is None
    assert body == md
