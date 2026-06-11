"""PDF -> DOCX conversion for make-paper (post-render, on user request).

Layout-preserving via pdf2docx, imported lazily so the rest of the renderer
works without it. The DOCX mirrors the rendered pages (columns, numbering,
table lines) but is layout-frozen — the Markdown stays the editable artifact.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def docx_available() -> str | None:
    """None if pdf2docx imports; else a warning with the install fix."""
    try:
        import pdf2docx  # noqa: F401
        return None
    except ImportError as e:
        return f"docx skipped ({e.name} not installed — pip install pdf2docx)"


def convert(pdf_path: Path, docx_path: Path | None = None) -> Path:
    """Convert a rendered PDF to DOCX; default target is <pdf name>.docx."""
    from pdf2docx import Converter

    pdf_path = Path(pdf_path)
    docx_path = Path(docx_path) if docx_path else pdf_path.with_suffix(".docx")
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    cv = Converter(str(pdf_path))
    try:
        cv.convert(str(docx_path))
    finally:
        cv.close()
    return docx_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make-paper PDF -> DOCX converter")
    parser.add_argument("--input", required=True, help="rendered paper PDF")
    parser.add_argument("--output", help="target DOCX path (default: input with .docx)")
    args = parser.parse_args(argv)

    missing = docx_available()
    if missing:
        print(missing, file=sys.stderr)
        return 2
    pdf = Path(args.input)
    if not pdf.is_file():
        print(f"input PDF not found: {pdf}", file=sys.stderr)
        return 1
    out = convert(pdf, Path(args.output) if args.output else None)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
