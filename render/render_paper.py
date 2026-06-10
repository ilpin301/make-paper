"""make-paper Subsystem B: render a German Markdown report into a styled PDF
via Pandoc + a custom LaTeX template (Tectonic engine), embedding Mermaid
diagrams and existing vault images."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

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
