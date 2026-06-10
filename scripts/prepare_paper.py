"""make-paper helper: resolve assets, stage samples, collect Wiki sources,
compute the German dateline, and emit a JSON manifest for the subagent."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

GERMAN_MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


def german_month(month: int) -> str:
    """Return the German month name for a 1-based month number."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    return GERMAN_MONTHS[month - 1]


def german_dateline(institution: str, today: date) -> str:
    """e.g. ('RWTH Aachen', 2026-06-10) -> 'RWTH Aachen, Juni 2026'."""
    return f"{institution}, {german_month(today.month)} {today.year}"


def parse_authors(md_text: str) -> tuple[list[str], str]:
    """Return (author_names, institution) parsed from an authors.md body."""
    names: list[str] = []
    institution = ""
    for raw in md_text.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            names.append(line[2:].strip())
        elif line.lower().startswith("institution:"):
            institution = line.split(":", 1)[1].strip()
    if not institution:
        for raw in md_text.splitlines():
            m = re.match(r"^(.*?),\s*[A-Za-zÄÖÜäöü]+\s+\d{4}\s*$", raw.strip())
            if m:
                institution = m.group(1).strip()
                break
    return names, institution


@dataclass
class Assets:
    samples_dir: Path
    authors_file: Path


def _has_files(d: Path) -> bool:
    return d.is_dir() and any(p.is_file() for p in d.iterdir())


def resolve_assets(project_path: Path, global_root: Path) -> Assets:
    """Hybrid resolution: project Samples/ + Authors/authors.md win; else global."""
    proj_samples = project_path / "Samples"
    glob_samples = global_root / "Samples"
    if _has_files(proj_samples):
        samples_dir = proj_samples
    elif _has_files(glob_samples):
        samples_dir = glob_samples
    else:
        raise FileNotFoundError(
            f"No samples in {proj_samples} or {glob_samples}"
        )

    proj_authors = project_path / "Authors" / "authors.md"
    glob_authors = global_root / "authors.md"
    if proj_authors.is_file():
        authors_file = proj_authors
    elif glob_authors.is_file():
        authors_file = glob_authors
    else:
        raise FileNotFoundError(
            f"No authors.md in {proj_authors} or {glob_authors}"
        )

    return Assets(samples_dir=samples_dir, authors_file=authors_file)


def collect_wiki_sources(project_path: Path) -> list[Path]:
    """All compiled Wiki notes (*.md under Wiki/), excluding index.md files."""
    wiki = project_path / "Wiki"
    if not wiki.is_dir():
        return []
    return sorted(
        p for p in wiki.rglob("*.md") if p.name.lower() != "index.md"
    )


def stage_samples(samples: list[Path], dest_dir: Path) -> list[Path]:
    """Copy each sample to dest as sample-NN.<ext> (1-based, zero-padded)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    width = max(2, len(str(len(samples))))
    staged: list[Path] = []
    for i, src in enumerate(samples, start=1):
        target = dest_dir / f"sample-{i:0{width}d}{src.suffix}"
        shutil.copyfile(src, target)
        staged.append(target)
    return staged


def build_manifest(project_path: Path, global_root: Path, staging_dir: Path,
                   today: date) -> dict:
    assets = resolve_assets(project_path, global_root)
    samples = sorted(p for p in assets.samples_dir.iterdir() if p.is_file())
    staged = stage_samples(samples, staging_dir)
    names, institution = parse_authors(
        assets.authors_file.read_text(encoding="utf-8")
    )
    return {
        "project_path": str(project_path),
        "wiki_sources": [str(p) for p in collect_wiki_sources(project_path)],
        "sample_sources": [str(p) for p in staged],
        "authors_source": str(assets.authors_file),
        "author_names": names,
        "dateline": german_dateline(institution, today),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="make-paper preparation helper")
    parser.add_argument("--project", required=True, help="path to the wiki project")
    parser.add_argument(
        "--global-root",
        default=str(Path.home() / ".claude" / "make-paper" / "assets"),
        help="fallback assets root",
    )
    parser.add_argument("--staging", required=True, help="dir for renamed samples")
    args = parser.parse_args(argv)
    manifest = build_manifest(
        project_path=Path(args.project),
        global_root=Path(args.global_root),
        staging_dir=Path(args.staging),
        today=date.today(),
    )
    json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
