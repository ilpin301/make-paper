# make-paper — Subsystem A (the agent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `make-paper` Claude Code subagent (pinned to Sonnet) plus a deterministic Python helper that turns any LLM-wiki project into a German-language NotebookLM **Markdown report**, downloaded into the project's `Papers/` folder.

**Architecture:** A main-session router gathers the NotebookLM profile + notebook name and delegates to the `make-paper` subagent. The subagent runs the project's maintenance gate, calls `prepare_paper.py` to resolve hybrid assets / stage samples / collect Wiki sources / compute the German dateline, then drives the `notebooklm` CLI to create a notebook, add sources, generate a German report, and download it as Markdown. (PDF rendering is subsystem B, a separate later plan; this plan stops at Markdown.)

**Tech Stack:** Python 3.14 (stdlib + pytest), the `notebooklm` CLI (`notebooklm-py`), Claude Code subagent markdown.

---

## File Structure

Repo root: `C:\Users\il720506\.claude\make-paper\` (its own git repo).

- Create: `scripts/prepare_paper.py` — deterministic helper (pure functions + thin CLI emitting a JSON manifest). One responsibility: turn a project path into everything the subagent needs.
- Create: `tests/test_prepare_paper.py` — pytest unit tests for the helper.
- Create: `assets/authors.md` — global fallback authors file.
- Create: `assets/Samples/.gitkeep` — global fallback samples folder (empty placeholder).
- Create: `agents/make-paper.md` — subagent definition (source of truth).
- Create: `README.md` — install + usage notes.
- Install copy: `C:\Users\il720506\.claude\agents\make-paper.md` (copied from `agents/make-paper.md` so Claude Code discovers it).

---

### Task 1: Initialize the make-paper repo and test tooling

**Files:**
- Create: `C:\Users\il720506\.claude\make-paper\.gitignore`

- [ ] **Step 1: Create the repo directory and init git**

Run (PowerShell):
```powershell
New-Item -ItemType Directory -Force "C:\Users\il720506\.claude\make-paper\scripts" | Out-Null
New-Item -ItemType Directory -Force "C:\Users\il720506\.claude\make-paper\tests" | Out-Null
New-Item -ItemType Directory -Force "C:\Users\il720506\.claude\make-paper\assets\Samples" | Out-Null
New-Item -ItemType Directory -Force "C:\Users\il720506\.claude\make-paper\agents" | Out-Null
git -C "C:\Users\il720506\.claude\make-paper" init
```
Expected: `Initialized empty Git repository ...` (or "Reinitialized" if it already exists).

- [ ] **Step 2: Write `.gitignore`**

Create `C:\Users\il720506\.claude\make-paper\.gitignore`:
```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
*.tmp
staging/
```

- [ ] **Step 3: Ensure pytest is installed**

Run:
```powershell
python -m pip install --quiet pytest
python -m pytest --version
```
Expected: prints a `pytest 8.x` (or similar) version line.

- [ ] **Step 4: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add .gitignore
git -C "C:\Users\il720506\.claude\make-paper" commit -m "chore: init make-paper tool repo"
```

---

### Task 2: German month names + dateline

**Files:**
- Create: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prepare_paper.py`:
```python
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prepare_paper as pp


def test_german_month_returns_native_name():
    assert pp.german_month(1) == "Januar"
    assert pp.german_month(3) == "März"
    assert pp.german_month(6) == "Juni"
    assert pp.german_month(12) == "Dezember"


def test_german_dateline_uses_current_month_and_year():
    line = pp.german_dateline("RWTH Aachen", date(2026, 6, 10))
    assert line == "RWTH Aachen, Juni 2026"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'prepare_paper'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/prepare_paper.py`:
```python
"""make-paper helper: resolve assets, stage samples, collect Wiki sources,
compute the German dateline, and emit a JSON manifest for the subagent."""
from __future__ import annotations

from datetime import date

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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: german month + dateline helper"
```

---

### Task 3: Parse `authors.md` (names + institution)

`authors.md` format the helper supports:
```markdown
# Authors
- Max Mustermann
- Erika Musterfrau

institution: RWTH Aachen
```
Fallback: if no `institution:` field exists, take the text before the comma on a
line that looks like `<institution>, <Month> <Year>`.

**Files:**
- Modify: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare_paper.py`:
```python
def test_parse_authors_reads_names_and_institution_field():
    md = "# Authors\n- Max Mustermann\n- Erika Musterfrau\n\ninstitution: RWTH Aachen\n"
    names, institution = pp.parse_authors(md)
    assert names == ["Max Mustermann", "Erika Musterfrau"]
    assert institution == "RWTH Aachen"


def test_parse_authors_falls_back_to_dateline_line():
    md = "- Max Mustermann\n\nRWTH Aachen, Juni 2026\n"
    names, institution = pp.parse_authors(md)
    assert names == ["Max Mustermann"]
    assert institution == "RWTH Aachen"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — `AttributeError: module 'prepare_paper' has no attribute 'parse_authors'`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/prepare_paper.py` (imports at top: `import re`):
```python
import re


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: parse authors.md names + institution"
```

---

### Task 4: Hybrid asset resolution (project overrides global)

**Files:**
- Modify: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare_paper.py`:
```python
def _make_sample(dirpath: Path, name: str):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text("x", encoding="utf-8")


def test_resolve_assets_prefers_project_over_global(tmp_path):
    project = tmp_path / "proj"
    glob = tmp_path / "global"
    _make_sample(project / "Samples", "a.md")
    (project / "Authors").mkdir(parents=True)
    (project / "Authors" / "authors.md").write_text("- A\ninstitution: X", encoding="utf-8")
    _make_sample(glob / "Samples", "g.md")
    (glob / "authors.md").write_text("- G\ninstitution: Y", encoding="utf-8")

    assets = pp.resolve_assets(project, glob)
    assert assets.samples_dir == project / "Samples"
    assert assets.authors_file == project / "Authors" / "authors.md"


def test_resolve_assets_falls_back_to_global(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    glob = tmp_path / "global"
    _make_sample(glob / "Samples", "g.md")
    (glob / "authors.md").write_text("- G\ninstitution: Y", encoding="utf-8")

    assets = pp.resolve_assets(project, glob)
    assert assets.samples_dir == glob / "Samples"
    assert assets.authors_file == glob / "authors.md"


def test_resolve_assets_raises_when_nothing_found(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    glob = tmp_path / "global"
    glob.mkdir()
    import pytest
    with pytest.raises(FileNotFoundError):
        pp.resolve_assets(project, glob)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — no attribute `resolve_assets`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/prepare_paper.py` (add `from dataclasses import dataclass` and `from pathlib import Path` at top):
```python
from dataclasses import dataclass
from pathlib import Path


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: hybrid asset resolution"
```

---

### Task 5: Collect compiled Wiki sources

**Files:**
- Modify: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare_paper.py`:
```python
def test_collect_wiki_sources_returns_md_excluding_index(tmp_path):
    wiki = tmp_path / "Wiki" / "Topics"
    wiki.mkdir(parents=True)
    (wiki / "a.md").write_text("a", encoding="utf-8")
    (wiki / "index.md").write_text("nav", encoding="utf-8")
    (tmp_path / "Wiki" / "Concepts").mkdir()
    (tmp_path / "Wiki" / "Concepts" / "b.md").write_text("b", encoding="utf-8")
    # noise outside Wiki/ must be ignored
    (tmp_path / "Raw").mkdir()
    (tmp_path / "Raw" / "c.md").write_text("c", encoding="utf-8")

    sources = pp.collect_wiki_sources(tmp_path)
    names = sorted(p.name for p in sources)
    assert names == ["a.md", "b.md"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — no attribute `collect_wiki_sources`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/prepare_paper.py`:
```python
def collect_wiki_sources(project_path: Path) -> list[Path]:
    """All compiled Wiki notes (*.md under Wiki/), excluding index.md files."""
    wiki = project_path / "Wiki"
    if not wiki.is_dir():
        return []
    return sorted(
        p for p in wiki.rglob("*.md") if p.name.lower() != "index.md"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: collect compiled Wiki sources"
```

---

### Task 6: Stage samples as `sample-01`, `sample-02`, …

**Files:**
- Modify: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare_paper.py`:
```python
def test_stage_samples_renames_zero_padded_keeps_extension(tmp_path):
    src = tmp_path / "Samples"
    src.mkdir()
    (src / "zeta.md").write_text("z", encoding="utf-8")
    (src / "alpha.docx").write_text("a", encoding="utf-8")
    dest = tmp_path / "staging"

    staged = pp.stage_samples([src / "alpha.docx", src / "zeta.md"], dest)
    names = [p.name for p in staged]
    assert names == ["sample-01.docx", "sample-02.md"]
    assert (dest / "sample-01.docx").read_text(encoding="utf-8") == "a"
    assert (dest / "sample-02.md").read_text(encoding="utf-8") == "z"
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — no attribute `stage_samples`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/prepare_paper.py` (add `import shutil` at top):
```python
import shutil


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: stage samples as sample-NN"
```

---

### Task 7: CLI `prepare` command → JSON manifest

The subagent calls this once. It resolves assets, stages samples into a staging
dir, collects Wiki sources, parses authors, computes the dateline, and prints a
JSON manifest to stdout.

**Files:**
- Modify: `scripts/prepare_paper.py`
- Test: `tests/test_prepare_paper.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prepare_paper.py`:
```python
import json
from datetime import date


def test_build_manifest_end_to_end(tmp_path):
    project = tmp_path / "proj"
    (project / "Wiki" / "Topics").mkdir(parents=True)
    (project / "Wiki" / "Topics" / "topic.md").write_text("t", encoding="utf-8")
    (project / "Samples").mkdir()
    (project / "Samples" / "ref.md").write_text("style", encoding="utf-8")
    (project / "Authors").mkdir()
    (project / "Authors" / "authors.md").write_text(
        "- Max Mustermann\ninstitution: RWTH Aachen\n", encoding="utf-8"
    )
    glob = tmp_path / "global"
    glob.mkdir()
    staging = tmp_path / "staging"

    manifest = pp.build_manifest(
        project_path=project, global_root=glob, staging_dir=staging,
        today=date(2026, 6, 10),
    )

    assert [Path(p).name for p in manifest["wiki_sources"]] == ["topic.md"]
    assert [Path(p).name for p in manifest["sample_sources"]] == ["sample-01.md"]
    assert Path(manifest["authors_source"]).name == "authors.md"
    assert manifest["author_names"] == ["Max Mustermann"]
    assert manifest["dateline"] == "RWTH Aachen, Juni 2026"
    # round-trips as JSON
    json.dumps(manifest)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: FAIL — no attribute `build_manifest`.

- [ ] **Step 3: Write minimal implementation**

Add to `scripts/prepare_paper.py` (add `import argparse`, `import json`, `import sys` at top):
```python
import argparse
import json
import sys


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
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```powershell
python -m pytest tests/test_prepare_paper.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add scripts/prepare_paper.py tests/test_prepare_paper.py
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: build_manifest + CLI entry point"
```

---

### Task 8: Global fallback assets

**Files:**
- Create: `assets/authors.md`
- Create: `assets/Samples/.gitkeep`

- [ ] **Step 1: Create the global authors fallback**

Create `C:\Users\il720506\.claude\make-paper\assets\authors.md`:
```markdown
# Authors

- Max Mustermann
- Erika Musterfrau

institution: RWTH Aachen
```

- [ ] **Step 2: Create the empty global samples placeholder**

Create `C:\Users\il720506\.claude\make-paper\assets\Samples\.gitkeep` (empty file).

- [ ] **Step 3: Verify the helper runs against the global fallback**

Run (uses global authors + a temp project with one Wiki note and a sample):
```powershell
$p = Join-Path $env:TEMP "mp_demo"
New-Item -ItemType Directory -Force "$p\Wiki\Topics" | Out-Null
New-Item -ItemType Directory -Force "$p\Samples" | Out-Null
Set-Content "$p\Wiki\Topics\t.md" "hello" -Encoding utf8
Set-Content "$p\Samples\ref.md" "style" -Encoding utf8
python "C:\Users\il720506\.claude\make-paper\scripts\prepare_paper.py" --project $p --staging "$p\staging"
```
Expected: prints JSON with `wiki_sources` (t.md), `sample_sources` (sample-01.md), `dateline` ending in the current German month + `2026`.

- [ ] **Step 4: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add assets
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: global fallback assets"
```

---

### Task 9: Write the `make-paper` subagent definition

**Files:**
- Create: `agents/make-paper.md`

- [ ] **Step 1: Write the subagent file**

Create `C:\Users\il720506\.claude\make-paper\agents\make-paper.md`:
```markdown
---
name: make-paper
description: >-
  Generates a German-language paper from an LLM-wiki project using NotebookLM.
  Use when the user says "make paper", "do paper", "make paper in notebook", or a
  close variant. PRECONDITION the MAIN agent MUST satisfy before delegating
  (this subagent cannot ask the user anything): ask the user (1) which notebooklm
  profile / Google account and (2) the desired notebook name, then delegate
  passing the project path, the profile, and the notebook name in the task
  prompt. When this agent returns, open the downloaded report for the user.
model: claude-sonnet-4-6
---

# make-paper

You generate a German-language paper from the current LLM-wiki project via the
`notebooklm` CLI. You run isolated: everything you need (project path, notebooklm
profile, notebook name) is in your task prompt. If any is missing, stop and
return an error asking the main agent to supply it — never attempt to ask the
user yourself.

Output of this subagent is a **German Markdown report** downloaded into the
project's `Papers/` folder. (Styled-PDF rendering is a separate tool, subsystem
B, and is out of scope here.)

## Steps (in order — stop and report on any failure)

1. **Maintenance gate.** From the project root, run the gate defined in the
   project's `AGENTS.md`:
   ```
   python scripts/wiki_tool.py doctor
   python scripts/wiki_tool.py build
   python scripts/wiki_tool.py lint
   python scripts/wiki_tool.py source-lint
   python scripts/audit_public.py
   ```
   If any command exits non-zero, ABORT and return its output. Do not touch
   NotebookLM on a failing vault.

2. **Verify NotebookLM auth for the requested profile.**
   ```
   notebooklm -p <profile> status
   ```
   If not authenticated, ABORT and report that the user must run
   `notebooklm -p <profile> login` once (browser OAuth) — you cannot do it.

3. **Prepare inputs.** Run the helper (paths are this tool's install location):
   ```
   python "%USERPROFILE%\.claude\make-paper\scripts\prepare_paper.py" \
     --project "<project_path>" --staging "<project_path>\Papers\.staging"
   ```
   Parse the JSON manifest: `wiki_sources`, `sample_sources`, `authors_source`,
   `author_names`, `dateline`.

4. **Create the notebook** in the requested profile:
   ```
   notebooklm -p <profile> create "<notebook_name>" --json
   ```
   Parse `.notebook.id` → NOTEBOOK_ID. Use `--notebook NOTEBOOK_ID` (or `-n`) on
   every later call — never rely on `use`.

5. **Add sources.** Add every `wiki_sources` file (the paper material), every
   `sample_sources` file (style refs, titled `sample-01`…), and `authors_source`:
   ```
   notebooklm -p <profile> source add "<file>" --notebook NOTEBOOK_ID --json
   ```
   Then wait until all sources are READY:
   ```
   notebooklm -p <profile> source list --notebook NOTEBOOK_ID --json
   ```

6. **Generate the German report** (custom prompt). Run:
   ```
   notebooklm -p <profile> generate report "<PROMPT>" --format custom \
     --language de --notebook NOTEBOOK_ID --json
   ```
   PROMPT (fill `<dateline>` and `<author_names>` from the manifest):
   > Schreibe ein wissenschaftliches Paper **auf Deutsch**, unabhängig von der
   > Sprache der Quellen (übersetze/synthetisiere bei Bedarf). Stütze den Inhalt
   > ausschließlich auf die bereitgestellten Quellen, deren Titel NICHT mit
   > „sample" beginnt. Übernimm aus den „sample*"-Quellen ausschließlich die
   > Dokumentstruktur, Gliederung und Abschnittsreihenfolge (nicht deren Inhalt).
   > Stelle strukturierte Daten als Markdown-Tabellen dar. Erfinde keine Daten
   > oder Werte. Setze als Autorenzeile genau: „<author_names>". Setze als
   > Institutszeile genau: „<dateline>".

   Parse `.task_id`, then wait:
   ```
   notebooklm -p <profile> artifact wait <task_id> -n NOTEBOOK_ID --timeout 900
   ```

7. **Download** the report into `Papers/`:
   ```
   notebooklm -p <profile> download report "<project_path>\Papers\<notebook_name>.md" \
     -n NOTEBOOK_ID
   ```

8. **Clean up** the staging dir `<project_path>\Papers\.staging`.

9. **Return a summary**: notebook ID/URL, the downloaded `.md` path, source
   counts, and a note that PDF rendering (subsystem B) is a separate step.
```

- [ ] **Step 2: Sanity-check the frontmatter parses**

Run:
```powershell
python -c "import re,sys; t=open(r'C:\Users\il720506\.claude\make-paper\agents\make-paper.md',encoding='utf-8').read(); assert t.startswith('---'); print('frontmatter ok')"
```
Expected: `frontmatter ok`.

- [ ] **Step 3: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add agents/make-paper.md
git -C "C:\Users\il720506\.claude\make-paper" commit -m "feat: make-paper subagent definition"
```

---

### Task 10: Install the subagent + README + manual end-to-end verification

**Files:**
- Create: `README.md`
- Install copy: `C:\Users\il720506\.claude\agents\make-paper.md`

- [ ] **Step 1: Write the README**

Create `C:\Users\il720506\.claude\make-paper\README.md`:
```markdown
# make-paper

Generate a German-language paper from any LLM-wiki project via NotebookLM.

## Install
1. `python -m pip install notebooklm-py pytest`
2. Authenticate each Google account as a profile, once:
   `notebooklm profile create <name>` then `notebooklm -p <name> login`
3. Copy the subagent into Claude Code's agents dir:
   `Copy-Item agents\make-paper.md $env:USERPROFILE\.claude\agents\make-paper.md -Force`

## Use
In any wiki project, say "make paper". The main agent asks which profile and
notebook name, then delegates to the `make-paper` subagent, which produces a
German Markdown report in the project's `Papers/` folder.

## Tests
`python -m pytest tests -v`

## Status
Subsystem A (this repo) produces Markdown. Styled-PDF rendering (Pandoc + LaTeX,
Mermaid/charts/images) is subsystem B — a separate plan.
```

- [ ] **Step 2: Run the full test suite**

Run:
```powershell
python -m pytest "C:\Users\il720506\.claude\make-paper\tests" -v
```
Expected: 10 passed.

- [ ] **Step 3: Install the subagent into Claude Code**

Run:
```powershell
Copy-Item "C:\Users\il720506\.claude\make-paper\agents\make-paper.md" "C:\Users\il720506\.claude\agents\make-paper.md" -Force
```
Then verify the file exists at the destination.

- [ ] **Step 4: Manual end-to-end check (requires NotebookLM auth)**

This step is interactive and needs a real authenticated profile; record the
outcome rather than asserting in code:
1. In the CLEAR vault (`F:\____IL_AI\CLEAR`), ensure a `Samples/` file and
   `Authors/authors.md` exist (or rely on the global fallback).
2. Say "make paper"; confirm the main agent asks for profile + notebook name.
3. Confirm the maintenance gate runs, a notebook is created, sources are added,
   a German report is generated, and `Papers/<name>.md` is downloaded.
4. Note any failures for follow-up.

- [ ] **Step 5: Commit**

```powershell
git -C "C:\Users\il720506\.claude\make-paper" add README.md
git -C "C:\Users\il720506\.claude\make-paper" commit -m "docs: README + install"
```

---

## Self-Review

**Spec coverage:**
- Trigger phrases → subagent `description` + router precondition (Task 9). ✓
- Maintenance gate first → Step 1 of subagent (Task 9). ✓
- Ask account + notebook name → router precondition in `description`; subagent
  consumes them (Task 9). ✓
- Hybrid samples/authors → `resolve_assets` (Task 4). ✓
- Compiled Wiki/ material only → `collect_wiki_sources` (Task 5). ✓
- Samples renamed sample-01… + authors.md added → `stage_samples` (Task 6) +
  subagent Step 5 (Task 9). ✓
- German output regardless of source language → `--language de` + German prompt
  (Task 9). ✓
- Current German month/year dateline → `german_dateline` (Task 2), injected via
  manifest (Task 7) into the prompt (Task 9). ✓
- Output downloaded into project → subagent Step 7 (Task 9). PDF + open: PDF is
  subsystem B (out of scope, documented); "open" is the router's job per the
  `description`. ✓ (PDF deferred by design.)

**Placeholder scan:** No TODO/TBD; every code step has full code; the subagent
prompt is complete German text. ✓

**Type consistency:** `Assets` dataclass fields (`samples_dir`, `authors_file`)
used consistently; manifest keys (`wiki_sources`, `sample_sources`,
`authors_source`, `author_names`, `dateline`) match between `build_manifest`
(Task 7) and the subagent's parse step (Task 9). ✓

**Note (carried to subsystem B):** the final PDF, the open-the-file step's target
being a PDF, and all graphics rendering (Mermaid/charts/images) are deferred to
subsystem B. Subsystem A intentionally stops at Markdown.
