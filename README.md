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
