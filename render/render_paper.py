"""make-paper Subsystem B: render a German Markdown report into a styled PDF
via Pandoc + a custom LaTeX template (Tectonic engine), embedding Mermaid
diagrams and existing vault images."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import preprocess as pre

REQUIRED_TOOLS = ["pandoc", "tectonic", "mmdc"]


def check_dependencies(which=shutil.which) -> list[str]:
    """Return the sorted list of REQUIRED_TOOLS not found on PATH."""
    return sorted(name for name in REQUIRED_TOOLS if which(name) is None)


def build_pandoc_cmd(input_path, output_path, template_path, resource_path,
                     *, layout: str = "one", to: str = "pdf") -> list[str]:
    """Construct the Pandoc argv: PDF via Tectonic, or a plain DOCX.

    The docx variant drops the LaTeX machinery (template, engine, lua filter,
    classoption) — pandoc's native writer handles headings, numbering, tables.
    """
    cmd = ["pandoc", str(input_path)]
    if to == "docx":
        cmd += ["--number-sections", f"--resource-path={resource_path}"]
        reference = Path(__file__).parent / "templates" / "reference.docx"
        if reference.is_file():
            cmd.append(f"--reference-doc={reference}")
    else:
        cmd += [
            "--template", str(template_path),
            "--pdf-engine=tectonic",
            "--number-sections",
            f"--resource-path={resource_path}",
            "--lua-filter", str(Path(__file__).parent / "filters" / "paper_style.lua"),
        ]
        if layout == "two":
            cmd += ["-V", "classoption=twocolumn"]
    cmd += ["-o", str(output_path)]
    return cmd


def run_mmdc(code: str, out_path, run=subprocess.run, which=shutil.which) -> None:
    """Render Mermaid `code` to `out_path` (PDF) using the mmdc CLI.

    Resolves `mmdc` via `which` because on Windows it is a `.cmd` shim, which
    CreateProcess cannot launch directly (only `.exe` is auto-resolved); such
    shims are run through `cmd /c`.
    """
    out_path = Path(out_path)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        src = Path(f.name)
    exe = which("mmdc") or "mmdc"
    args = [exe, "-i", str(src), "-o", str(out_path), "-b", "transparent"]
    if exe.lower().endswith((".cmd", ".bat")):
        args = ["cmd", "/c", *args]
    try:
        run(args, check=True)
    finally:
        src.unlink(missing_ok=True)


def run_paperchart(code: str, out_path) -> Path | None:
    """Parse + render one paperchart block; None (and a warning) on failure."""
    import charts

    try:
        spec = charts.parse_paperchart(code)
        charts.render_chart(spec, out_path)
        return Path(out_path), spec.title
    except charts.ChartSpecError as e:
        print(f"paperchart skipped: {e}", file=sys.stderr)
        return None
    except Exception as e:  # matplotlib failures etc. — never fatal
        print(f"paperchart render failed: {e}", file=sys.stderr)
        return None


def run_autochart(spec, out_path) -> Path | None:
    """Render one auto-detected chart spec; None (and a warning) on failure."""
    import charts

    try:
        charts.render_chart(spec, out_path)
        return Path(out_path)
    except Exception as e:
        print(f"autochart render failed: {e}", file=sys.stderr)
        return None


def render(input_md, output_pdf, project_root, *, title=None, authors=None,
           dateline=None, work_dir=None, run=subprocess.run, mmdc_runner=None,
           layout: str = "one", charts: str = "blocks", to: str = "pdf") -> Path:
    """Full pipeline: preprocess the report Markdown and render it to a PDF
    (default) or a DOCX (`to="docx"`: PNG figures, no LaTeX styling pass)."""
    input_md = Path(input_md)
    output_pdf = Path(output_pdf)
    project_root = Path(project_root)
    work_dir = Path(work_dir) if work_dir else output_pdf.parent / ".render"
    work_dir.mkdir(parents=True, exist_ok=True)

    md = input_md.read_text(encoding="utf-8")
    md = pre.strip_heading_numbers(md)
    extracted_title, md = pre.extract_title(md)
    abstract, md = pre.extract_abstract(md)
    md = pre.strip_author_lines(md, authors or "", dateline or "")
    if abstract:
        # NotebookLM also repeats author/institution lines inside the
        # abstract section (styling rule v2.3-3)
        abstract = pre.strip_author_lines(abstract, authors or "",
                                          dateline or "").strip()
    md = pre.promote_headings(md)
    md = pre.move_references_last(md)
    md, _missing = pre.resolve_images(md, project_root)

    import charts as charts_mod

    figures = work_dir / "figures"
    ext = "png" if to == "docx" else "pdf"   # Word can't embed PDF figures
    if charts != "off" and (warn := charts_mod.charts_available()):
        print(warn, file=sys.stderr)
        charts = "off"
    if charts == "off":
        md, _ = pre.render_paperchart_blocks(md, figures, lambda code, p: None)
    else:
        md, n_blocks = pre.render_paperchart_blocks(md, figures, run_paperchart,
                                                    ext=ext)
        if charts == "auto" and n_blocks == 0:
            md = pre.inject_autodetected_charts(
                md, figures, run_autochart, charts_mod.autodetect_charts, ext=ext
            )

    md = pre.render_mermaid_blocks(md, work_dir / "figures",
                                   mmdc_runner or run_mmdc, ext=ext)

    meta = {
        "title": title or extracted_title or "",
        "author": authors or "",
        "dateline": dateline or "",
        # one paragraph: the abstract lives inside the \twocolumn[{...}] head
        "abstract": re.sub(r"\s+", " ", abstract).strip() if abstract else "",
    }
    if to == "docx":
        # the docx writer shows `date` in the title block; `dateline` is a
        # template-only variable that would be dropped silently
        meta["date"] = dateline or ""
    processed = pre.build_frontmatter(meta) + md
    processed_path = work_dir / "processed.md"
    processed_path.write_text(processed, encoding="utf-8")

    template = Path(__file__).parent / "templates" / "paper.latex"
    cmd = build_pandoc_cmd(processed_path, output_pdf, template, project_root,
                           layout=layout, to=to)
    run(cmd, check=True)
    return output_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make-paper Subsystem B renderer")
    parser.add_argument("--input", required=True, help="report Markdown from Subsystem A")
    parser.add_argument("--output", required=True, help="target PDF path")
    parser.add_argument("--project", required=True, help="project root (for images)")
    parser.add_argument("--title", help="override the title (else first H1)")
    parser.add_argument("--authors", help="author line, e.g. 'A 123, B 456'")
    parser.add_argument("--dateline", help="institution dateline, e.g. 'RWTH Aachen, Juni 2026'")
    parser.add_argument("--layout", choices=["one", "two"], default="one",
                        help="page layout: one or two columns")
    parser.add_argument("--charts", choices=["auto", "blocks", "off"], default="blocks",
                        help="paperchart handling: blocks only, +autodetect fallback, or off")
    args = parser.parse_args(argv)

    missing = check_dependencies()
    if missing:
        print(f"Missing tools: {', '.join(missing)}", file=sys.stderr)
        return 2

    out = render(
        args.input, args.output, args.project,
        title=args.title, authors=args.authors, dateline=args.dateline,
        layout=args.layout, charts=args.charts,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
