import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))

import render_paper as rp


def test_check_dependencies_reports_missing():
    present = {"pandoc"}
    fake_which = lambda name: "/usr/bin/" + name if name in present else None
    missing = rp.check_dependencies(which=fake_which)
    assert missing == ["mmdc", "tectonic"]


def test_check_dependencies_none_missing():
    fake_which = lambda name: "/usr/bin/" + name
    assert rp.check_dependencies(which=fake_which) == []


def test_build_pandoc_cmd_has_template_and_tectonic():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj")
    assert cmd[0] == "pandoc"
    assert "in.md" in cmd
    assert "--template" in cmd and "tpl.latex" in cmd
    assert "--pdf-engine=tectonic" in cmd
    assert "--number-sections" in cmd
    assert "--resource-path=/proj" in cmd
    assert cmd[-2:] == ["-o", "out.pdf"]


def test_run_mmdc_invokes_mmdc_with_io(tmp_path):
    seen = {}

    def fake_run(argv, check):
        seen["argv"] = argv
        seen["check"] = check

    out = tmp_path / "d.pdf"
    rp.run_mmdc("graph TD; A-->B", out, run=fake_run, which=lambda name: name)
    assert seen["argv"][0] == "mmdc"
    assert "-i" in seen["argv"] and "-o" in seen["argv"]
    assert str(out) in seen["argv"]
    assert seen["check"] is True


import subprocess
import pytest


@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
def test_template_compiles_minimal_doc(tmp_path):
    template = Path(rp.__file__).parent / "templates" / "paper.latex"
    md = tmp_path / "doc.md"
    md.write_text(
        '---\ntitle: "Test"\nauthor: "Max Mustermann"\n'
        'dateline: "RWTH Aachen, Juni 2026"\nabstract: |\n  Eine Kurzfassung.\n---\n\n'
        "# Abschnitt\n\nText mit Umlauten: äöü.\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\nTabelle oben.\n",
        encoding="utf-8",
    )
    out = tmp_path / "doc.pdf"
    cmd = rp.build_pandoc_cmd(md, out, template, tmp_path)
    subprocess.run(cmd, check=True)
    assert out.is_file() and out.stat().st_size > 1000


def test_render_pipeline_writes_processed_md_and_calls_pandoc(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    report = project / "report.md"
    report.write_text(
        "# Mein Titel\n\n## Zusammenfassung\nKurz.\n\n## 1. Einleitung\nText.\n\n"
        "```mermaid\ngraph TD; A-->B\n```\n",
        encoding="utf-8",
    )
    calls = {}

    def fake_run(cmd, check):
        calls["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"%PDF-fake-output")

    def fake_mmdc(code, out_path):
        Path(out_path).write_bytes(b"%PDF-fake-diagram")

    out_pdf = project / "out.pdf"
    result = rp.render(
        report, out_pdf, project,
        title=None, authors="Max Mustermann", dateline="RWTH Aachen, Juni 2026",
        run=fake_run, mmdc_runner=fake_mmdc,
    )
    assert result == out_pdf
    processed = (project / ".render" / "processed.md").read_text(encoding="utf-8")
    assert 'title: "Mein Titel"' in processed
    assert 'author: "Max Mustermann"' in processed
    assert "abstract: |" in processed
    assert "# Einleitung" in processed        # number stripped, level promoted
    assert "```mermaid" not in processed      # diagram replaced
    assert calls["cmd"][0] == "pandoc"
    assert str(out_pdf) in calls["cmd"]


def test_main_errors_when_tools_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rp, "check_dependencies", lambda which=None: ["tectonic"])
    rc = rp.main([
        "--input", str(tmp_path / "r.md"),
        "--output", str(tmp_path / "o.pdf"),
        "--project", str(tmp_path),
    ])
    assert rc == 2
    assert "tectonic" in capsys.readouterr().err


@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
def test_end_to_end_render_real_pdf(tmp_path):
    import pypdf
    fixture = Path(__file__).parent / "fixtures" / "report_de.md"
    out = tmp_path / "paper.pdf"
    rp.render(
        fixture, out, tmp_path,
        authors="Petr Nasybulin 478314, Philipp Gembruch 472685",
        dateline="RWTH Aachen, Juni 2026",
    )
    assert out.is_file() and out.stat().st_size > 2000
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) >= 1
    text = "".join((p.extract_text() or "") for p in reader.pages)
    # ligature-free terms (the serif font renders 'ffi' as one glyph)
    assert "Absorptionsspektroskopie" in text
    assert "Lambert-Beersche" in text


import shutil

TABLE_MD = (
    "| Komponente | Pfad |\n|---|---|\n| Wiki | /wiki |\n| Schema | /schema |\n| Skripte | /scripts |\n"
    "\nText.\n\n"
    "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |\n| 5 | 6 | 7 | 8 |\n| 9 | 10 | 11 | 12 |\n"
)

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")


WIDE_CELL_MD = (
    "\n| Komponente | Beschreibung |\n|---|---|\n"
    "| Wiki | Ein sehr langer Beschreibungstext der die Zeile weit ueber "
    "zweiundsiebzig Zeichen hinaus verlaengert |\n"
)


@needs_pandoc
def test_paper_style_filter_tables_and_equations(tmp_path):
    filt = Path(rp.__file__).parent / "filters" / "paper_style.lua"
    src = tmp_path / "t.md"
    src.write_text(
        TABLE_MD + WIDE_CELL_MD + "\nFormel:\n\n$$E = m c^2$$\n\n![Testtitel](bild.pdf)\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(filt)],
        capture_output=True, text=True, check=True,
    ).stdout
    # tables: floats, centered, no longtable leftovers
    assert "longtable" not in out
    assert out.count("\\begin{table}[t]") == 1    # narrow 2-col -> column float
    # 4-col table AND wide-celled 2-col table -> spanning floats (rule v2.3-2)
    assert out.count("\\begin{table*}[t]") == 2
    assert "\\endhead" not in out and "\\endlastfoot" not in out
    # full grid: vertical lines incl. the outer edges (rule v2.3-4)
    assert "{|c|c|}" in out                # simple 2-col table
    assert "{|c|c|c|c|}" in out            # simple 4-col table
    assert re.search(r"\\real\{[\d.]+\}\}\|", out)     # width-managed columns
    assert re.search(r"\\real\{[\d.]+\}\}\|\}", out)   # ... incl. outer edge
    # booktabs rules replaced by \hline so verticals meet horizontals
    assert "\\toprule" not in out and "\\bottomrule" not in out
    assert "\\hline" in out
    assert out.index("Skripte") < out.rindex("\\hline")
    # light-blue header row on every table (rule v2.3-4)
    assert out.count("\\rowcolor{tableheadbg}") == 3
    # display math: numbered equation, no plain \[ block
    assert "\\begin{equation}" in out and "E = m c^2" in out
    assert "\\[" not in out
    # captioned image survives as a figure with caption
    assert "\\caption{Testtitel" in out


@needs_pandoc
def test_paper_style_filter_references_full_width(tmp_path):
    filt = Path(rp.__file__).parent / "filters" / "paper_style.lua"
    src = tmp_path / "r.md"
    src.write_text(
        "# Einleitung\n\nText.\n\n# Literaturverzeichnis {-}\n\n*[1] Quelle*\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(filt)],
        capture_output=True, text=True, check=True,
    ).stdout
    # two-column layout switches to one column for the references (rule v2.3-1)
    switch = "\\if@twocolumn\\onecolumn\\fi"
    assert switch in out
    assert out.index(switch) < out.index("Literaturverzeichnis")


def test_build_pandoc_cmd_two_column_adds_filter_and_classoption():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="two")
    i = cmd.index("--lua-filter")
    assert cmd[i + 1].endswith("paper_style.lua")
    j = cmd.index("-V")
    assert cmd[j + 1] == "classoption=twocolumn"
    assert cmd[-2:] == ["-o", "out.pdf"]


def test_build_pandoc_cmd_one_column_has_filter_but_no_classoption():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="one")
    i = cmd.index("--lua-filter")
    assert cmd[i + 1].endswith("paper_style.lua")
    assert "-V" not in cmd


def test_build_pandoc_cmd_docx_has_no_latex_machinery():
    cmd = rp.build_pandoc_cmd("in.md", "out.docx", None, "/proj", to="docx")
    assert cmd[0] == "pandoc"
    assert "--template" not in cmd
    assert "--pdf-engine=tectonic" not in cmd
    assert "--lua-filter" not in cmd and "-V" not in cmd
    assert "--number-sections" in cmd
    assert "--resource-path=/proj" in cmd
    assert cmd[-2:] == ["-o", "out.docx"]


def test_build_pandoc_cmd_docx_uses_reference_doc():
    cmd = rp.build_pandoc_cmd("in.md", "out.docx", None, "/proj", to="docx")
    ref = [a for a in cmd if str(a).startswith("--reference-doc=")]
    assert ref and ref[0].endswith("reference.docx")


def test_render_docx_uses_png_figures_and_date_metadata(tmp_path):
    src = tmp_path / "r.md"
    src.write_text("# Titel\n\n```mermaid\ngraph TD; A-->B\n```\n", encoding="utf-8")
    calls = {}

    def fake_run(cmd, check):
        calls["pandoc"] = cmd

    rp.render(src, tmp_path / "out.docx", tmp_path, run=fake_run,
              mmdc_runner=lambda code, p: None,
              dateline="RWTH, Juni 2026", to="docx")
    processed = (tmp_path / ".render" / "processed.md").read_text(encoding="utf-8")
    assert "mermaid-" in processed and ".png)" in processed
    assert 'date: "RWTH, Juni 2026"' in processed   # docx title block shows date
    assert "--template" not in calls["pandoc"]
    assert str(tmp_path / "out.docx") in calls["pandoc"]


def test_run_paperchart_returns_none_on_bad_spec(tmp_path, capsys):
    result = rp.run_paperchart("kaputt: [", tmp_path / "c.pdf")
    assert result is None
    assert "paperchart skipped" in capsys.readouterr().err


def _render_with_stubs(tmp_path, md_text, **kwargs):
    """Run rp.render with pandoc/mmdc stubbed out; return processed.md + calls."""
    src = tmp_path / "report.md"
    src.write_text(md_text, encoding="utf-8")
    out_pdf = tmp_path / "out.pdf"
    calls = {}

    def fake_run(cmd, check):
        calls["pandoc"] = cmd

    rp.render(
        src, out_pdf, tmp_path, run=fake_run,
        mmdc_runner=lambda code, p: Path(p).write_bytes(b"%PDF-"),
        **kwargs,
    )
    processed = (tmp_path / ".render" / "processed.md").read_text(encoding="utf-8")
    return processed, calls


GOOD_BLOCK = "```paperchart\ntype: bar\nlabels: [a, b, c]\nseries: [{values: [1, 2, 3]}]\n```\n"
CHARTABLE_TABLE = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n"


def test_render_charts_off_strips_blocks(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + GOOD_BLOCK, charts="off")
    assert "paperchart" not in processed and "![](" not in processed


needs_chart_deps = pytest.mark.skipif(
    __import__("charts").charts_available() is not None, reason="chart deps missing"
)


@needs_chart_deps
def test_render_charts_blocks_renders_figures(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + GOOD_BLOCK, charts="blocks")
    assert "![](" in processed and "chart-" in processed


@needs_chart_deps
def test_render_charts_auto_falls_back_to_autodetect(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + CHARTABLE_TABLE, charts="auto")
    assert "autochart-" in processed


@needs_chart_deps
def test_render_charts_auto_no_fallback_when_blocks_exist(tmp_path):
    md = "# T\n\n" + GOOD_BLOCK + "\n" + CHARTABLE_TABLE
    processed, _ = _render_with_stubs(tmp_path, md, charts="auto")
    assert "chart-" in processed and "autochart-" not in processed


def test_render_two_column_uses_filter(tmp_path):
    _, calls = _render_with_stubs(tmp_path, "# T\n\nText.\n", layout="two")
    assert any(str(a).endswith("paper_style.lua") for a in calls["pandoc"])
    assert "classoption=twocolumn" in calls["pandoc"]


@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
@needs_chart_deps
def test_two_column_pdf_with_autochart_end_to_end(tmp_path):
    md = tmp_path / "report.md"
    md.write_text(
        "# Zweispaltiger Testbericht\n\n"
        "## Zusammenfassung\nKurzfassung des Berichts.\n\n"
        "## Messwerte\n\n"
        "| Indexgröße | p50 | p99 |\n|---|---|---|\n"
        "| 10k | 12 | 40 |\n| 100k | 18 | 95 |\n| 1M | 35 | 210 |\n\n"
        "## Architektur\n\n"
        "| A | B | C | D |\n|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 |\n| 5 | 6 | 7 | 8 |\n| 9 | 1 | 2 | 3 |\n\n"
        "Fließtext danach mit Umlauten: äöüß.\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.pdf"
    rp.render(md, out, tmp_path, authors="Test Autor 123456",
              dateline="RWTH Aachen, Juni 2026", layout="two", charts="auto")
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 10_000
    assert list((tmp_path / ".render" / "figures").glob("autochart-*.pdf"))


def test_render_pipeline_applies_styling_steps(tmp_path):
    md_text = (
        "# Titel\n\n**Anna Autor 1**\n**RWTH, Juni 2026**\n\n"
        "### Abstract\nKurz.  \nZweite Zeile.\n\n"
        "### Literaturverzeichnis\n1. Quelle Eins\n\n"
        "### Einleitung\nText.\n"
    )
    processed, _ = _render_with_stubs(
        tmp_path, md_text, authors="Anna Autor 1", dateline="RWTH, Juni 2026"
    )
    assert "Anna Autor 1" in processed.split("---")[1]   # only in frontmatter
    assert "**Anna Autor 1**" not in processed
    assert "# Einleitung" in processed                    # promoted H3 -> H1
    assert processed.rstrip().endswith("*[1] Quelle Eins*")
    assert "# Literaturverzeichnis {-}" in processed
    assert "abstract:" in processed and "Zweite Zeile." in processed


def test_template_has_v22_styling_declarations():
    template = (Path(rp.__file__).parent / "templates" / "paper.latex").read_text(encoding="utf-8")
    # rule 1: abstract gets a section-style, unnumbered heading
    assert "\\section*{Abstract}" in template
    # rule 2: dot after first-level section numbers only (no 1..1 leak)
    assert "\\renewcommand{\\thesection}{\\arabic{section}.}" in template
    assert "\\renewcommand{\\thesubsection}{\\arabic{section}.\\arabic{subsection}}" in template
    # rule 4 support: booktabs rules must meet the new vertical lines
    assert "\\setlength{\\aboverulesep}{0pt}" in template
    assert "\\setlength{\\belowrulesep}{0pt}" in template


def test_render_strips_author_lines_inside_abstract(tmp_path):
    md_text = (
        "# Titel\n\n## Abstract\nKurzfassung des Versuchs.\n\n"
        "Autoren: Anna Autor\nInstitution: RWTH Aachen\n\n## Einleitung\nText.\n"
    )
    processed, _ = _render_with_stubs(
        tmp_path, md_text, authors="Anna Autor 1", dateline="RWTH Aachen, Juni 2026"
    )
    front = processed.split("---")[1]
    assert "Kurzfassung des Versuchs." in front
    assert "Autoren" not in front and "Institution" not in front


def test_template_has_v23_styling_declarations():
    template = (Path(rp.__file__).parent / "templates" / "paper.latex").read_text(encoding="utf-8")
    # rule 1: body text flush left (head keeps its own alignment)
    assert "\\RaggedRight" in template
    # rule 2: no hyphenation anywhere; abstract stays justified via stretch
    assert "\\hyphenpenalty=10000" in template
    assert "\\exhyphenpenalty=10000" in template
    assert "\\emergencystretch=3em" in template
    # rule 4: light-blue table header rows, captions tight under the table
    assert "\\usepackage[table]{xcolor}" in template
    assert "\\definecolor{tableheadbg}{RGB}{217,226,243}" in template
    assert "\\captionsetup[table]{skip=4pt}" in template
    # addendum: one regular space between section number and heading text
    assert ("\\renewcommand{\\@seccntformat}[1]"
            "{\\csname the#1\\endcsname\\space}") in template


@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
@pytest.mark.parametrize("layout", ["one", "two"])
def test_template_compiles_both_layouts_with_styling(tmp_path, layout):
    md = tmp_path / "doc.md"
    md.write_text(
        "# Stiltest\n\n### Abstract\nKursive Kurzfassung.\n\n"
        "### Einleitung\nText mit Formel:\n\n$$E = m c^2$$\n\n"
        "#### Methodik\nUnterabschnitt.\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n\n"
        "### Literaturverzeichnis\n1. Eine Quelle. Aachen.\n2. Zweite Quelle. Bonn.\n",
        encoding="utf-8",
    )
    out = tmp_path / f"doc-{layout}.pdf"
    rp.render(md, out, tmp_path, authors="Anna Autor 1", dateline="RWTH, Juni 2026",
              layout=layout, charts="off")
    assert out.read_bytes()[:5] == b"%PDF-"
    import pypdf
    text = "".join((p.extract_text() or "") for p in pypdf.PdfReader(str(out)).pages)
    assert "Abstract" in text          # rule 1: heading is rendered again
    assert "1..1" not in text          # rule 2: dot only on first level
    assert "1.1" in text               # subsection numbering intact
