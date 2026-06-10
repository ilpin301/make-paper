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
German Markdown report in the project's `Papers/` folder **and automatically
renders it to a styled PDF** (Subsystem B). If the PDF toolchain isn't installed,
it falls back to the Markdown and tells you what to install. The main agent then
opens the PDF (or the Markdown).

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
  --dateline "<dateline from A's manifest>"
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

### Status / scope
v1: tables + Mermaid + existing images, single-column. Deferred to v2:
auto-generated data charts; faithful two-column layout (needs a longtable→table*
Lua filter to survive LaTeX twocolumn).
