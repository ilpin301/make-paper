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


def test_render_paperchart_blocks_replaces_with_captioned_figure(tmp_path):
    def runner(code, out_path):
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path, "Mein Diagramm"

    out, count = pre.render_paperchart_blocks(PAPERCHART_MD, tmp_path, runner)
    assert count == 1
    assert "```paperchart" not in out
    assert "![Mein Diagramm](" in out and ".pdf)" in out
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
    class FakeSpec:
        title = "Autotitel"

    fake_spec = FakeSpec()

    def detect(text):
        return [(fake_spec, 4)]  # last table line index

    def runner(spec, out_path):
        assert spec is fake_spec
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out = pre.inject_autodetected_charts(md, tmp_path, runner, detect)
    lines = out.splitlines()
    fig_idx = next(i for i, l in enumerate(lines) if l.startswith("![Autotitel]("))
    assert fig_idx > 4
    assert lines.index("Danach.") > fig_idx


def test_inject_autodetected_charts_skips_failed_renders(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n"
    out = pre.inject_autodetected_charts(
        md, tmp_path, lambda spec, p: None, lambda text: [(object(), 4)]
    )
    assert "![](" not in out


AUTHORS = "Petr Nasybulin 478314, Philipp Gembruch 472685"
DATELINE = "RWTH Aachen, Juni 2026"


def test_strip_author_lines_removes_bold_duplicates():
    md = f"**{AUTHORS}**\n**{DATELINE}**\n\n## Einleitung\nText über {DATELINE}.\n"
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    assert AUTHORS not in out.split("## Einleitung")[0]
    assert "## Einleitung" in out
    assert f"Text über {DATELINE}." in out


def test_strip_author_lines_only_before_first_heading():
    md = f"## Anhang\n{AUTHORS}\n"
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    assert AUTHORS in out


def test_strip_author_lines_removes_labeled_variants():
    md = (
        "Autoren: Petr Nasybulin (478314) und Philipp Gembruch (472685)\n"
        "**Institution:** RWTH Aachen\n\n## Einleitung\nText.\n"
    )
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    before = out.split("## Einleitung")[0]
    assert "Autoren" not in before and "Institution" not in before
    assert "## Einleitung" in out


def test_strip_author_lines_keeps_sentences_mentioning_institution():
    md = ("Die Versuche wurden im Praktikum der RWTH Aachen "
          "durchgeführt und ausgewertet.\n\n## Einleitung\n")
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    assert "Praktikum der RWTH Aachen" in out


def test_strip_author_lines_noop_without_matches():
    md = "Ganz normaler Text.\n\n## Einleitung\n"
    assert pre.strip_author_lines(md, AUTHORS, DATELINE) == md


def test_strip_author_lines_noop_with_empty_args():
    md = f"**{AUTHORS}**\n\n## E\n"
    assert pre.strip_author_lines(md, "", "") == md


def test_promote_headings_shifts_h3_to_h1():
    md = "### Einleitung\nText\n#### Detail\n### Fazit\n"
    out = pre.promote_headings(md)
    assert "# Einleitung" in out and "## Detail" in out and "# Fazit" in out
    assert "###" not in out


def test_promote_headings_noop_when_h1_present():
    md = "# Einleitung\n### Detail\n"
    assert pre.promote_headings(md) == md


def test_promote_headings_ignores_code_fences():
    md = "```paperchart\n### not a heading\n```\n## Echt\n"
    out = pre.promote_headings(md)
    assert "### not a heading" in out and "# Echt" in out


REFS_MD = (
    "# Einleitung\nText.\n\n"
    "# Literaturverzeichnis\n"
    "1. RWTH Aachen: Anleitung. Aachen.\n"
    "2. Messprotokoll intern.\n\n"
    "# Fazit\nSchluss.\n"
)


def test_move_references_last_moves_and_renumbers():
    out = pre.move_references_last(REFS_MD)
    assert out.rstrip().endswith("*[2] Messprotokoll intern.*")
    assert "*[1] RWTH Aachen: Anleitung. Aachen.*" in out
    assert "1. RWTH" not in out
    assert out.index("# Fazit") < out.index("# Literaturverzeichnis {-}")


def test_move_references_handles_bullets_and_alt_titles():
    md = "# A\n\n## Quellen\n- Erste Quelle\n- Zweite Quelle\n\n# B\nText.\n"
    out = pre.move_references_last(md)
    assert out.index("# B") < out.index("# Literaturverzeichnis {-}")
    assert "*[1] Erste Quelle*" in out and "*[2] Zweite Quelle*" in out


def test_move_references_noop_when_absent():
    md = "# A\nText ohne Quellenangaben.\n"
    assert pre.move_references_last(md) == md


def test_figure_helpers_honor_png_ext(tmp_path):
    out = pre.render_mermaid_blocks(
        "```mermaid\ngraph TD; A-->B\n```\n", tmp_path,
        lambda code, p: None, ext="png")
    assert "mermaid-" in out and ".png)" in out and ".pdf" not in out

    out, n = pre.render_paperchart_blocks(
        "```paperchart\ntype: bar\n```\n", tmp_path,
        lambda code, p: (p, "Titel"), ext="png")
    assert n == 1 and "chart-" in out and ".png)" in out and ".pdf" not in out

    spec = type("Spec", (), {"title": "T"})()
    out = pre.inject_autodetected_charts(
        "| a |\n|---|\n| 1 |", tmp_path,
        lambda s, p: p, lambda md: [(spec, 2)], ext="png")
    assert "autochart-01.png" in out


def test_move_references_entries_each_start_a_new_line():
    out = pre.move_references_last(REFS_MD)
    # hard line break (trailing backslash) after every entry but the last,
    # so entries don't flow into one paragraph (styling rule v2.2)
    assert "*[1] RWTH Aachen: Anleitung. Aachen.*\\\n*[2] Messprotokoll intern.*" in out
    assert not out.rstrip().endswith("\\")
