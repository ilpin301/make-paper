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


def test_extract_abstract_pulls_named_section():
    md = (
        "## Zusammenfassung\n"
        "Dies ist die Kurzfassung.\n\n"
        "## Einleitung\n"
        "Der eigentliche Text.\n"
    )
    abstract, body = pre.extract_abstract(md)
    assert abstract == "Dies ist die Kurzfassung."
    assert "Zusammenfassung" not in body
    assert "## Einleitung" in body


def test_extract_abstract_returns_none_when_absent():
    md = "## Einleitung\nText\n"
    abstract, body = pre.extract_abstract(md)
    assert abstract is None
    assert body == md


def test_resolve_images_rewrites_existing_relative_paths(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(b"x")
    md = "![Abb](img/a.png) und ![Fehlt](img/missing.png) und ![Web](https://x/y.png)"
    out, missing = pre.resolve_images(md, tmp_path)
    assert (tmp_path / "img" / "a.png").as_posix() in out
    assert "img/missing.png" in out          # left untouched
    assert "https://x/y.png" in out          # URL untouched
    assert missing == ["img/missing.png"]


def test_iter_mermaid_blocks_returns_code():
    md = "Vor\n```mermaid\ngraph TD; A-->B\n```\nNach\n"
    assert pre.iter_mermaid_blocks(md) == ["graph TD; A-->B"]


def test_render_mermaid_blocks_replaces_with_image(tmp_path):
    md = "```mermaid\ngraph TD; A-->B\n```\n"
    calls = []

    def fake_runner(code, out_path):
        calls.append((code, out_path))
        Path(out_path).write_bytes(b"%PDF-fake")

    out = pre.render_mermaid_blocks(md, tmp_path / "figures", fake_runner)
    assert "```mermaid" not in out
    assert "![](" in out
    assert len(calls) == 1
    assert calls[0][0] == "graph TD; A-->B"


def test_build_frontmatter_quotes_scalars_and_blocks_abstract():
    meta = {
        "title": 'Titel mit "Anführung"',
        "author": "Petr Nasybulin 478314, Philipp Gembruch 472685",
        "dateline": "RWTH Aachen, Juni 2026",
        "abstract": "Zeile eins.\nZeile zwei.",
    }
    fm = pre.build_frontmatter(meta)
    assert fm.startswith("---\n")
    assert fm.rstrip().endswith("---")
    assert 'title: "Titel mit \\"Anführung\\""' in fm
    assert "author: \"Petr Nasybulin 478314, Philipp Gembruch 472685\"" in fm
    assert "dateline: \"RWTH Aachen, Juni 2026\"" in fm
    assert "abstract: |" in fm
    assert "  Zeile eins." in fm
    assert "  Zeile zwei." in fm


def test_build_frontmatter_omits_empty_fields():
    fm = pre.build_frontmatter({"title": "T", "author": "", "dateline": "", "abstract": ""})
    assert "title:" in fm
    assert "author:" not in fm
    assert "abstract:" not in fm


PAPERCHART_MD = (
    "Vorher.\n\n"
    "```paperchart\ntype: bar\nlabels: [a]\nseries: [{values: [1]}]\n```\n\n"
    "Nachher.\n"
)


def test_render_paperchart_blocks_replaces_with_figure(tmp_path):
    def runner(code, out_path):
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out, count = pre.render_paperchart_blocks(PAPERCHART_MD, tmp_path, runner)
    assert count == 1
    assert "```paperchart" not in out
    assert "![](" in out and ".pdf)" in out
    assert "Vorher." in out and "Nachher." in out


def test_render_paperchart_blocks_drops_failed_block(tmp_path):
    out, count = pre.render_paperchart_blocks(
        PAPERCHART_MD, tmp_path, lambda code, out_path: None
    )
    assert count == 1
    assert "```paperchart" not in out
    assert "![](" not in out


def test_render_paperchart_blocks_counts_all_blocks(tmp_path):
    md = PAPERCHART_MD + "\n```paperchart\nkaputt: [\n```\n"
    out, count = pre.render_paperchart_blocks(md, tmp_path, lambda c, p: None)
    assert count == 2


def test_inject_autodetected_charts_inserts_after_table(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n\nDanach.\n"
    fake_spec = object()

    def detect(text):
        return [(fake_spec, 4)]  # last table line index

    def runner(spec, out_path):
        assert spec is fake_spec
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out = pre.inject_autodetected_charts(md, tmp_path, runner, detect)
    lines = out.splitlines()
    fig_idx = next(i for i, l in enumerate(lines) if l.startswith("![]("))
    assert fig_idx > 4
    assert lines.index("Danach.") > fig_idx


def test_inject_autodetected_charts_skips_failed_renders(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n"
    out = pre.inject_autodetected_charts(
        md, tmp_path, lambda spec, p: None, lambda text: [(object(), 4)]
    )
    assert "![](" not in out
