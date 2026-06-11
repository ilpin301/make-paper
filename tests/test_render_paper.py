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
    assert "## Einleitung" in processed       # number stripped
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


@needs_pandoc
def test_lua_filter_converts_tables_to_floats(tmp_path):
    filt = Path(rp.__file__).parent / "filters" / "twocolumn_tables.lua"
    src = tmp_path / "t.md"
    src.write_text(TABLE_MD, encoding="utf-8")
    out = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(filt)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "longtable" not in out
    assert "\\begin{tabular}" in out
    assert "\\begin{table}[t]" in out      # 2-column table -> column float
    assert "\\begin{table*}[t]" in out     # 4-column table -> spanning float
    assert "\\endhead" not in out and "\\endlastfoot" not in out
    # \bottomrule must come after the body rows, before \end{tabular}
    assert out.index("Skripte") < out.index("\\bottomrule")
