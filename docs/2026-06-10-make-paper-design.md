# make-paper — Design Spec

**Date:** 2026-06-10
**Status:** Approved (design), pending implementation plan
**Author:** ilpin301@gmail.com

## Summary

`make-paper` is a reusable Claude Code tool that turns the compiled knowledge in
any LLM-wiki project into a finished **German-language PDF paper**, generated in
Google NotebookLM. It is triggered by natural-language phrases such as
"make paper" / "do paper" / "make paper in notebook". The paper's *content* comes
from the project's compiled `Wiki/` notes; its *style* (fonts, structure, graphic
styling) is copied from sample documents; and its author list + institution
dateline come from an `authors.md` file.

The tool works across **all** wiki projects, not just CLEAR — it relies on the
shared wiki conventions (`AGENTS.md` maintenance gate, `scripts/wiki_tool.py`,
two-layer `Raw/` → `Wiki/` structure) rather than anything project-specific.

## Goals

- One trigger phrase produces a complete, styled, German PDF paper with correct
  authors and a current-dated institution line.
- Run the project's full maintenance gate first, so a paper is never built on a
  vault that fails its own quality checks.
- Keep heavy, token-intensive work on a cheaper model (Sonnet) for cost control.
- Be portable across every wiki project via a hybrid local/global asset lookup.

## Non-Goals

- No editing of NotebookLM output by hand inside this flow (download is final).
- No support for non-wiki projects.
- No multi-paper batch generation in a single run (one paper per invocation).

## Architecture

Because Claude Code **subagents cannot ask the end user questions mid-run**
(`AskUserQuestion` is blocked in subagents) but **can** pin a cheap model and
invoke skills, the tool is split into two parts:

### 1. Main-session router (runs on the session model, e.g. Opus)

Responsibilities:
- Recognize trigger phrases: "make paper", "do paper", "make paper in notebook",
  and close variants.
- Ask the user the two interactive questions a subagent cannot:
  1. **Which Google account** to create the notebook in.
  2. **Notebook name.**
- Dispatch the `make-paper` subagent with: `{ project_path, google_account,
  notebook_name }`.
- When the subagent returns, **open the downloaded PDF**.

### 2. `make-paper` subagent (pinned to Sonnet)

- Location: `~/.claude/agents/make-paper.md` (user-level → available in every
  project).
- Frontmatter: `model: claude-sonnet-4-6`; tools inherited (so the `Skill` tool
  and the `notebooklm` skill are available); a `description` that makes the main
  agent delegate on the trigger phrases.
- Receives the account + notebook name from the router (it must never try to ask
  the user; if either is missing it returns an error for the router to handle).

## Subagent workflow (ordered)

1. **Maintenance gate.** Run the current project's `AGENTS.md` gate:
   ```
   python scripts/wiki_tool.py doctor
   python scripts/wiki_tool.py build
   python scripts/wiki_tool.py lint
   python scripts/wiki_tool.py source-lint
   python scripts/audit_public.py
   ```
   If any step fails, **abort** and return the failing output. Do not create a
   notebook on a failing vault.

2. **Resolve style + author inputs (hybrid).**
   - Samples: use project `Samples/` if it contains files; else fall back to the
     global `~/.claude/make-paper/Samples/`.
   - Authors: use project `Authors/authors.md` if present; else fall back to the
     global `~/.claude/make-paper/authors.md`.
   - If neither project nor global source exists for a required input, abort with
     a clear message.

3. **Create the notebook** via the `notebooklm` skill, in the provided Google
   account, with the provided name.

4. **Upload material.** Upload the project's **compiled `Wiki/` notes only**
   (Topics, Concepts, Entities, Projects, Logs) as NotebookLM sources. Do not
   upload `Raw/`, `Schema/`, `_templates/`, or sample files as "material".

5. **Add style + author sources.**
   - Copy each Samples file into the notebook, renamed `sample-01`, `sample-02`,
     … — zero-padded index, ordered by original filename, original file
     extension preserved.
   - Copy `authors.md` into the notebook.

6. **Send the generation prompt.** The prompt instructs NotebookLM to:
   - Write the paper **entirely in German**, regardless of the language of the
     source material (translate/synthesize as needed).
   - Base the paper's **content** on all provided material **except** any source
     named `sample*`.
   - Take **style, fonts, document structure, and graphic styling** from the
     `sample*` files.
   - Take **all author names** from `authors.md` and present them as in the
     sample.
   - Emit the **institution dateline** (e.g. "RWTH Aachen, …") using the
     **current month and year written in German** (e.g. "Juni 2026"). The current
     date is computed at run time, and the German month name is always used even
     if the source/authors file used another language.

7. **Download** the generated paper as **PDF** into the project's `Papers/`
   folder (created if absent).

8. **Return a summary**: notebook URL and the local PDF path.

### Main session, after subagent returns

- Open the downloaded PDF.

## Data / asset conventions

| Asset | Project location | Global fallback |
|---|---|---|
| Style samples | `Samples/` | `~/.claude/make-paper/Samples/` |
| Authors + dateline | `Authors/authors.md` | `~/.claude/make-paper/authors.md` |
| Paper material | `Wiki/` (compiled notes) | n/a (always project) |
| Output | `Papers/*.pdf` | n/a (always project) |

- `authors.md` contains the author names and an institution dateline line such as
  `RWTH Aachen, Juni 2026`; the month + year are overridden with the current date
  at generation time (German month name).

## Generation prompt (draft)

> Erstelle ein wissenschaftliches Paper **auf Deutsch**. Schreibe das gesamte
> Dokument auf Deutsch, unabhängig von der Sprache des Quellmaterials (übersetze
> bzw. synthetisiere bei Bedarf).
>
> Inhalt: Stütze dich auf alle bereitgestellten Quellen **außer** den Dateien mit
> Namen `sample*`.
>
> Stil: Übernimm aus den `sample*`-Dateien das Layout, die Schriftarten, die
> Dokumentstruktur und – falls vorhanden – den Stil der Grafiken.
>
> Autoren: Übernimm alle Namen aus `authors.md` und stelle sie wie im Sample dar.
> Setze die Institutszeile (z. B. „RWTH Aachen, …") mit dem **aktuellen Monat und
> Jahr auf Deutsch** (z. B. „Juni 2026").

(Final wording tuned during implementation; current month/year injected at run
time.)

## Model choice

- Subagent pinned to **`claude-sonnet-4-6`** — much cheaper than Opus, reliable
  enough for the multi-step NotebookLM + file orchestration. May later be tried
  on Haiku once the flow is proven.
- The main-session router runs on whatever the session model is; its work is
  minimal (phrase detection + two questions + open file).

## Dependencies to verify during implementation

The design assumes the `notebooklm` skill supports, in some form:
1. Creating a notebook in a **specified Google account**.
2. **Uploading** local files as sources.
3. Sending a **generation/chat prompt** to produce a paper artifact.
4. **Exporting/downloading** the artifact as **PDF**.

If any capability is missing or differs, the implementation plan adapts (e.g.
different export format, or a manual step). This is the main implementation risk.

## Error handling

- Maintenance gate failure → abort before any NotebookLM action; return the
  failing command output.
- Missing samples/authors (no project and no global) → abort with guidance to
  create them.
- Missing account or notebook name reaching the subagent → return error to the
  router (subagent cannot prompt the user).
- NotebookLM step failure → return the error and the partial state (e.g. notebook
  created but generation failed) so the user can recover.

## Open questions / future

- Whether to also keep an editable (DOCX/Markdown) copy alongside the PDF.
- Whether `Papers/` filenames should encode the notebook name + date.
- Whether to support multiple authors files / paper templates per project.

---

## Revisions (planning phase, 2026-06-10)

After inspecting the actual `notebooklm` CLI (`notebooklm-py`) and the local
machine, these decisions supersede earlier sections where they conflict.

### NotebookLM reality

- `notebooklm` is a **CLI**. "Which Google account" = a **named profile**
  (`notebooklm profile create <name>`; one-time `notebooklm -p <name> login`
  browser OAuth). The router selects/ensures the profile.
- Notebook: `notebooklm create "Name" --json` → `.notebook.id`.
- Sources: `notebooklm source add <file> --notebook <id>` (Markdown supported).
- **No "paper" artifact and no styled-PDF export.** The document artifact is
  `generate report`, which downloads as **Markdown only**
  (`notebooklm download report ./out.md`). The only native PDF is a slide-deck
  (slides, not a paper).
- German output: `notebooklm generate report --language de` (or global
  `notebooklm language set de`).
- A report is **text + Markdown tables only** — no inline images, charts, or
  diagrams. Per `AGENTS.md` "never invent": NotebookLM may only tabulate/chart
  data that already exists in the `Wiki/` sources.

### Resulting two-subsystem split

The original single flow is split into two independently-buildable subsystems
with a clean `.md → .pdf` interface:

- **Subsystem A — the agent (built first).** The `make-paper` subagent + main-
  session router + NotebookLM orchestration. Produces a **German Markdown
  report** and downloads it. Useful on its own.
- **Subsystem B — render pipeline (separate later plan).** Converts the German
  Markdown report into a **styled PDF** using **Pandoc + LaTeX**, with a LaTeX
  template derived from the sample (the template is where fonts/layout/graphic
  styling live). Renders Mermaid diagrams, data-driven charts (existing data
  only), and embeds existing vault images.

### Division of labor for styling

- NotebookLM imitates the sample's **section structure** in German Markdown and
  emits tables; where appropriate it emits **Mermaid** code blocks and chart
  **data** (only from existing sources).
- The **LaTeX template** (subsystem B) supplies fonts, layout, and visual style.
  NotebookLM cannot copy a sample's *look*.

### Graphics scope (subsystem B)

Tables (reliable) + Mermaid diagrams (best-effort) + data-driven charts (only
from numbers already in `Wiki/`) + embedding images that already exist in the
vault. No generated photos/drawings; no invented data.

### Local toolchain

Present: **Node/npm/npx**, **Python 3.14**. Missing: pandoc, LaTeX, LibreOffice,
Chrome/weasyprint. Subsystem B's plan must install **Pandoc + a LaTeX
distribution (MiKTeX)** and a Mermaid renderer (`@mermaid-js/mermaid-cli` via the
available Node) for the pandoc mermaid filter.

### Model

Subagent pinned to `claude-sonnet-4-6` (confirmed).

### Tool layout

- Repo/source root: `~/.claude/make-paper/` (own git repo).
- Subagent source: `~/.claude/make-paper/agents/make-paper.md`, **installed**
  (copied) to `~/.claude/agents/make-paper.md` so Claude Code discovers it.
- Deterministic helper: `~/.claude/make-paper/scripts/prepare_paper.py`
  (hybrid asset resolution, sample staging → `sample-01.<ext>`, Wiki source
  collection, German dateline). Unit-tested with pytest.
- Global fallback assets: `~/.claude/make-paper/assets/Samples/`,
  `~/.claude/make-paper/assets/authors.md`.
