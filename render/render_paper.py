"""make-paper Subsystem B: render a German Markdown report into a styled PDF
via Pandoc + a custom LaTeX template (Tectonic engine), embedding Mermaid
diagrams and existing vault images."""
from __future__ import annotations

import argparse
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


def build_pandoc_cmd(input_path, output_path, template_path, resource_path) -> list[str]:
    """Construct the Pandoc argv for a single-column German PDF via Tectonic."""
    return [
        "pandoc",
        str(input_path),
        "--template", str(template_path),
        "--pdf-engine=tectonic",
        "--number-sections",
        f"--resource-path={resource_path}",
        "-o", str(output_path),
    ]


def run_mmdc(code: str, out_path, run=subprocess.run) -> None:
    """Render Mermaid `code` to `out_path` (PDF) using the mmdc CLI."""
    out_path = Path(out_path)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        src = Path(f.name)
    try:
        run(["mmdc", "-i", str(src), "-o", str(out_path), "-b", "transparent"], check=True)
    finally:
        src.unlink(missing_ok=True)


def render(input_md, output_pdf, project_root, *, title=None, authors=None,
           dateline=None, work_dir=None, run=subprocess.run, mmdc_runner=None) -> Path:
    """Full pipeline: preprocess the report Markdown and render it to a PDF."""
    input_md = Path(input_md)
    output_pdf = Path(output_pdf)
    project_root = Path(project_root)
    work_dir = Path(work_dir) if work_dir else output_pdf.parent / ".render"
    work_dir.mkdir(parents=True, exist_ok=True)

    md = input_md.read_text(encoding="utf-8")
    md = pre.strip_heading_numbers(md)
    extracted_title, md = pre.extract_title(md)
    abstract, md = pre.extract_abstract(md)
    md, _missing = pre.resolve_images(md, project_root)
    md = pre.render_mermaid_blocks(md, work_dir / "figures", mmdc_runner or run_mmdc)

    meta = {
        "title": title or extracted_title or "",
        "author": authors or "",
        "dateline": dateline or "",
        "abstract": abstract or "",
    }
    processed = pre.build_frontmatter(meta) + md
    processed_path = work_dir / "processed.md"
    processed_path.write_text(processed, encoding="utf-8")

    template = Path(__file__).parent / "templates" / "paper.latex"
    cmd = build_pandoc_cmd(processed_path, output_pdf, template, project_root)
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
    args = parser.parse_args(argv)

    missing = check_dependencies()
    if missing:
        print(f"Missing tools: {', '.join(missing)}", file=sys.stderr)
        return 2

    out = render(
        args.input, args.output, args.project,
        title=args.title, authors=args.authors, dateline=args.dateline,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
