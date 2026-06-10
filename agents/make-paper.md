---
name: make-paper
description: >-
  Generates a German-language paper from an LLM-wiki project using NotebookLM.
  Use when the user says "make paper", "do paper", "make paper in notebook", or a
  close variant. PRECONDITION the MAIN agent MUST satisfy before delegating
  (this subagent cannot ask the user anything): ask the user (1) which notebooklm
  profile / Google account and (2) the desired notebook name, then delegate
  passing the project path, the profile, and the notebook name in the task
  prompt. When this agent returns, open the produced PDF for the user (or the
  Markdown report if it reports that PDF rendering was skipped).
model: claude-sonnet-4-6
---

# make-paper

You generate a German-language paper from the current LLM-wiki project via the
`notebooklm` CLI. You run isolated: everything you need (project path, notebooklm
profile, notebook name) is in your task prompt. If any is missing, stop and
return an error asking the main agent to supply it — never attempt to ask the
user yourself.

Output of this subagent is a **German Markdown report** downloaded into the
project's `Papers/` folder, which you then **render to a styled PDF** via the
Subsystem-B renderer (`render/render_paper.py`). The Markdown is the canonical
artifact; the PDF is a rendering of it. If the PDF toolchain is unavailable, the
Markdown still stands on its own.

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

8. **Render the PDF (Subsystem B).** Join `author_names` from the manifest with
   `", "` into AUTHOR_LINE, then run the renderer:
   ```
   python "%USERPROFILE%\.claude\make-paper\render\render_paper.py" \
     --input  "<project_path>\Papers\<notebook_name>.md" \
     --output "<project_path>\Papers\<notebook_name>.pdf" \
     --project "<project_path>" \
     --authors "<AUTHOR_LINE>" --dateline "<dateline>"
   ```
   This needs `pandoc`, `tectonic`, and `mmdc` on PATH (Tectonic fetches packages
   on first run). Handle the result:
   - Exit 0 (prints `Wrote …pdf`): the PDF is the primary deliverable.
   - Exit 2 (prints `Missing tools: …`) or any other failure: do NOT abort. The
     Markdown report is already downloaded and is the deliverable; record that PDF
     rendering was skipped and include the renderer's message (e.g. which tools to
     install: `winget install JohnMacFarlane.Pandoc TectonicProject.Tectonic` and
     `npm install -g @mermaid-js/mermaid-cli`).

9. **Clean up** the staging dir `<project_path>\Papers\.staging` and the
   renderer's work dir `<project_path>\Papers\.render`.

10. **Return a summary**: notebook ID/URL, the downloaded `.md` path, the rendered
    `.pdf` path (or a clear note that PDF rendering was skipped + why), and source
    counts. Tell the main agent which file to open — the `.pdf` if it was produced,
    otherwise the `.md`.
