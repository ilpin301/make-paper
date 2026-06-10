"""make-paper Subsystem B: render a German Markdown report into a styled PDF
via Pandoc + a custom LaTeX template (Tectonic engine), embedding Mermaid
diagrams and existing vault images."""
from __future__ import annotations

import shutil

REQUIRED_TOOLS = ["pandoc", "tectonic", "mmdc"]


def check_dependencies(which=shutil.which) -> list[str]:
    """Return the sorted list of REQUIRED_TOOLS not found on PATH."""
    return sorted(name for name in REQUIRED_TOOLS if which(name) is None)
