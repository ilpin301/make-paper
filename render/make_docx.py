"""Markdown -> DOCX conversion for make-paper (post-render, on user request).

Runs the same preprocess pipeline as the PDF renderer but targets pandoc's
native docx writer: real heading styles, editable flowing text, PNG figures.
The LaTeX-only looks (two-column, dotted numbering, table rules) don't carry
over — the DOCX is the editable companion, the PDF stays the styled artifact.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import render_paper as rp


def docx_available() -> str | None:
    """None if pandoc is on PATH; else a warning with the install fix."""
    if shutil.which("pandoc") is None:
        return ("docx skipped (pandoc not on PATH — "
                "winget install JohnMacFarlane.Pandoc)")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make-paper Markdown -> DOCX converter")
    parser.add_argument("--input", required=True, help="report Markdown from Subsystem A")
    parser.add_argument("--output", help="target DOCX path (default: input with .docx)")
    parser.add_argument("--project", required=True, help="project root (for images)")
    parser.add_argument("--title", help="override the title (else first H1)")
    parser.add_argument("--authors", help="author line, e.g. 'A 123, B 456'")
    parser.add_argument("--dateline", help="institution dateline, e.g. 'RWTH Aachen, Juni 2026'")
    parser.add_argument("--charts", choices=["auto", "blocks", "off"], default="blocks",
                        help="paperchart handling, same as the PDF renderer")
    args = parser.parse_args(argv)

    missing = docx_available()
    if missing:
        print(missing, file=sys.stderr)
        return 2
    src = Path(args.input)
    if not src.is_file():
        print(f"input Markdown not found: {src}", file=sys.stderr)
        return 1

    out = rp.render(
        src, Path(args.output) if args.output else src.with_suffix(".docx"),
        args.project,
        title=args.title, authors=args.authors, dateline=args.dateline,
        charts=args.charts, to="docx",
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
