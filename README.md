# make-paper

Generate a German-language paper from any LLM-wiki project via NotebookLM.

## Setup on a new machine

Prerequisites: Claude Code, Python 3.10+, Node.js (only for Mermaid
diagrams), git. The steps are Windows-flavored (PowerShell); macOS/Linux
should work analogously but is untested.

1. **Clone this repo — the path matters.** The subagent invokes the helper
   scripts by this absolute path:
   ```powershell
   git clone https://github.com/ilpin301/make-paper.git "$env:USERPROFILE\.claude\make-paper"
   ```
2. **Install the subagent** (Claude Code picks up anything in `~/.claude/agents/`):
   ```powershell
   Copy-Item "$env:USERPROFILE\.claude\make-paper\agents\make-paper.md" "$env:USERPROFILE\.claude\agents\make-paper.md" -Force
   ```
3. **Python packages:**
   ```powershell
   python -m pip install notebooklm-py pyyaml matplotlib python-docx
   ```
   (`notebooklm-py` = Subsystem A; `pyyaml`+`matplotlib` = charts —
   missing chart deps degrade to a no-chart paper, never a failure;
   `python-docx` = the DOCX option's two-column layout. Add `pytest` to
   run the test suite.)
4. **PDF toolchain** (see "Subsystem B install" below for the no-winget
   fallback; the DOCX option needs only pandoc + `python-docx`):
   ```powershell
   winget install JohnMacFarlane.Pandoc TectonicProject.Tectonic
   npm install -g @mermaid-js/mermaid-cli
   ```
   Tectonic downloads LaTeX packages + fonts on its first run (needs
   internet once). If the toolchain is missing, the subagent degrades to
   the Markdown report and tells you what to install.
5. **NotebookLM login — once per machine, per Google account** (browser
   OAuth; cookies are stored locally, nothing can be copied over):
   ```powershell
   notebooklm profile create <name>
   notebooklm -p <name> login
   ```
6. **Have a vault.** The project you write the paper from must be on the
   machine too, with its structure: `Wiki/` notes, the `AGENTS.md`
   maintenance gate (`scripts/wiki_tool.py`, `scripts/audit_public.py`),
   and optionally `Samples/` + `Autors/autors.md` — if absent, the global
   fallbacks in `~/.claude/make-paper/assets/` are used (drop your sample
   paper and authors file there once).

Note: the agent has a built-in proxy workaround for machines whose system
proxy is a local VPN SOCKS port; on machines with normal internet it stays
out of the way.

## Use
In any wiki project, say "make paper". The main agent asks which profile,
notebook name, layout (one/two-column), and whether to include charts, then
delegates to the `make-paper` subagent, which produces a German Markdown
report in the project's `Papers/` folder **and automatically renders it to a
styled PDF** (Subsystem B). If the PDF toolchain isn't installed, it falls
back to the Markdown and tells you what to install. The main agent then opens
the PDF (or the Markdown), runs a graphics review loop (chart edits are
local re-renders), and finally asks "Make DOCX?" — on yes it builds an
editable Word version via `render/make_docx.py` (pandoc docx writer styled
like the PDF via `templates/reference.docx`: Times, paper sizes/margins,
italic abstract, table borders; PNG figures; `--layout two` gives a
two-column body under a full-width title head).

## Tests
`python -m pytest tests -v`

## Status
Subsystem A produces the German Markdown report. Subsystem B (below) renders it
to a styled PDF.

## Subsystem B — render to PDF

The subagent runs this automatically after the report downloads. To render a
report by hand (or re-render after edits):

```powershell
python "$env:USERPROFILE\.claude\make-paper\render\render_paper.py" `
  --input  "<project>\Papers\<name>.md" `
  --output "<project>\Papers\<name>.pdf" `
  --project "<project>" `
  --authors "<author_names from A's manifest, comma-joined>" `
  --dateline "<dateline from A's manifest>" `
  --layout two --charts auto
```

Requires `pandoc`, `tectonic`, and `mmdc` on PATH (see install below). The renderer
strips manual heading numbers (LaTeX renumbers), lifts the title and abstract,
resolves relative image paths against the project, renders ```` ```mermaid ````
blocks via `mmdc`, and compiles a single-column German paper with Tectonic.

### Subsystem B install
```powershell
winget install JohnMacFarlane.Pandoc
winget install TectonicProject.Tectonic
npm install -g @mermaid-js/mermaid-cli
```
If `winget`'s source is unavailable, download the portable `pandoc.exe` and
`tectonic.exe` from their GitHub releases, drop them in a folder, and add it to
PATH. (Tectonic fetches LaTeX packages + the TeX Gyre Termes font on first run.)

### v2: charts + two-column

- `--layout one|two` (default `one`): two-column uses `classoption=twocolumn`
  plus `render/filters/paper_style.lua` (tables become `table`/`table*`
  floats; pandoc's `longtable` cannot live inside `twocolumn`).
- `--charts auto|blocks|off` (default `blocks`): renders ```` ```paperchart ````
  YAML blocks (bar/line/pie) via matplotlib to vector PDF figures; `auto` adds
  table auto-detection as fallback when the report has no blocks; `off`
  strips blocks. Soft deps: `pip install pyyaml matplotlib` — missing deps
  skip charts with a warning, never fail the render.
- Chart edits after a run are local: edit the ```` ```paperchart ```` blocks in
  `Papers/<name>.md`, re-run the renderer.

### v2.1 + v2.2: styling rules

Always applied: italic full-width abstract under an unnumbered section-style
"Abstract" heading; authors/dateline only at the title block; references end
the paper as unnumbered "Literaturverzeichnis" with italic `[1] …` entries,
one per line; display formulas numbered `(1)`, `(2)`; table cells centered
(H+V) in floats with vertical lines between columns; figures captioned
"Abbildung N: <Titel>" (bold label, footnotesize); sections numbered
1. / 1.1 / 1.1.1 (dot after first level only).

### Status / scope
v1: tables + Mermaid + existing images, single-column.
v2 (built): paperchart data charts + per-run two-column layout.
v2.1 + v2.2 (built): the styling rules above.
DOCX option (built): post-run "Make DOCX?" → editable Word via pandoc.
