---
name: make-paper
description: >-
  Generates a German-language paper from an LLM-wiki project using NotebookLM.
  Use when the user says "make paper", "do paper", "make paper in notebook", or a
  close variant. PRECONDITION the MAIN agent MUST satisfy before delegating
  (this subagent cannot ask the user anything), asking in this order:
  FIRST ask the dialog language (1. English, 2. Deutsch, 3. Русский) and then
  conduct ALL further main-session interaction — the prompt-mode question, the
  questions below, the graphics review, the "Make DOCX?" question, and every
  status/summary message — in the chosen language (the paper itself always stays
  German regardless of this choice; do not pass the language to the subagent).
  SECOND ask how to generate the NotebookLM prompt (1. Default, 2. I already
  have my own prompt, 3. Let's discuss this): on 1 use the default prompt; on 2
  ask the user to provide their prompt (paste a block or give a file path), load
  the text, and pass it as PROMPT_OVERRIDE in the task prompt; on 3 invoke the
  grIL-me skill to discuss it, then re-ask this prompt-mode question (it resolves
  to 1 or 2 — there is no automatic hand-off of the discussion).
  THEN ask the user (1) which notebooklm
  profile / Google account, (2) the desired notebook name, (3) layout: one- or
  two-column, and (4) whether to include data charts; and (5) check the
  project's Samples/ folder (then the global fallback
  %USERPROFILE%\.claude\make-paper\assets\Samples\): if it has NO files,
  proceed without asking — the built-in house style (render templates) applies
  by default; if it DOES contain files, ask the user what to do with them
  (use as structure/genre samples as usual, ignore them, or follow other
  instructions) and pass that decision in the task prompt. Then delegate
  passing the project path, profile, notebook name, layout, charts choice,
  the samples decision, and PROMPT_OVERRIDE (only if the user supplied one)
  in the task prompt. When this agent returns, open the produced PDF for the user (or the
  Markdown report if it reports that PDF rendering was skipped), then ask the
  user what to change in the graphics (remove/add/retype charts); apply chart
  changes by editing the paperchart blocks in Papers/<name>.md and re-running
  render/render_paper.py with the same flags — a local loop, no NotebookLM calls.
  AFTER the graphics review is settled, ask the user "Make DOCX?"; on yes run
  `python "%USERPROFILE%\.claude\make-paper\render\make_docx.py" --input
  "<project>\Papers\<name>.md" --project "<project>" --authors "<AUTHOR_LINE>"
  --dateline "<dateline>" --charts <same as render> --layout <same as render>`
  (pandoc docx writer from the Markdown, styled like the PDF via
  templates/reference.docx: Times, paper sizes/margins, italic abstract, PNG
  figures, two-column body with full-width head when layout two — local,
  exit 2 = pandoc missing) and open the resulting DOCX. Re-run it after any
  later chart edits so the DOCX matches.
model: claude-sonnet-4-6
---

# make-paper

You generate a German-language paper from the current LLM-wiki project via the
`notebooklm` CLI. You run isolated: everything you need (project path, notebooklm
profile, notebook name) is in your task prompt. If any is missing, stop and
return an error asking the main agent to supply it — never attempt to ask the
user yourself. The task prompt MAY also carry an optional `PROMPT_OVERRIDE` (a
user-supplied NotebookLM prompt); when present it replaces the default content
prompt in Step 6 (the structural rules are still appended). It is optional —
its absence is the normal Default case.

Output of this subagent is a **German Markdown report** downloaded into the
project's `Papers/` folder, which you then **render to a styled PDF** via the
Subsystem-B renderer (`render/render_paper.py`). The Markdown is the canonical
artifact; the PDF is a rendering of it. If the PDF toolchain is unavailable, the
Markdown still stands on its own.

## Network / proxy workaround (Windows + local VPN)

On this machine the Windows system proxy may be a local VPN's SOCKS port (e.g.
`socks=127.0.0.1:10808`). That breaks two things:

- `notebooklm` (Python/httpx) mis-parses the registry `socks=` entry as
  `socks4://` and fails with `Unknown scheme for proxy URL`; without any proxy
  NotebookLM may geo-block with `location=unsupported`.
- `tectonic` (render step) ignores the system proxy and its bundle fetches fail
  with DNS errors for `relay.fullyjustified.net`.

The VPN port is mixed-mode and accepts HTTP CONNECT, so the fix for both is the
same env override, set **in the same shell invocation** as the command (shell
state does not persist between tool calls). Determine the port from the system
proxy if set:

```powershell
(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').ProxyServer
# e.g. "socks=127.0.0.1:10808" → PROXY_URL = http://127.0.0.1:10808
```

Then prefix every `notebooklm` call and the renderer call:

```powershell
$env:ALL_PROXY='<PROXY_URL>'; $env:HTTPS_PROXY='<PROXY_URL>'; $env:HTTP_PROXY='<PROXY_URL>'; <command>
```

Rules: if a system `socks=` proxy is configured, apply the override from the
start. If no system proxy is set, run commands plainly — but if one then fails
with `Unknown scheme for proxy URL`, `location=unsupported`, or a DNS/bundle
fetch error, retry it once with the override (using port 10808 as the default)
before reporting failure. Do NOT use a `socks5://` URL (socksio not installed).

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

2. **Verify NotebookLM auth for the requested profile** (proxy override per the
   network section above, here and on every later `notebooklm` call):
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
   `sample_sources` file (style refs, titled `sample-01`…), and `authors_source`.
   Samples decision from the task prompt: if it says to IGNORE the samples,
   skip the `sample_sources` uploads (and drop the sample-related sentences
   from the PROMPT in step 6) — the visual style always comes from the
   built-in render templates either way. If no samples exist, that is the
   normal default case: proceed without them.
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
   The PROMPT is CONTENT + STRUCTURE. CONTENT is the default paragraph below in
   Default mode, OR — if the task prompt carries a `PROMPT_OVERRIDE` — that
   override text verbatim instead of the default paragraph. STRUCTURE is the
   always-appended block(s) below; appended in BOTH modes so the renderer never
   breaks.

   CONTENT — default paragraph (Default mode; fill `<dateline>` and
   `<author_names>` from the manifest):
   > Schreibe ein wissenschaftliches Paper **auf Deutsch**, unabhängig von der
   > Sprache der Quellen (übersetze/synthetisiere bei Bedarf). Stütze den Inhalt
   > ausschließlich auf die bereitgestellten Quellen, deren Titel NICHT mit
   > „sample" beginnt. Übernimm aus den „sample*"-Quellen ausschließlich die
   > Dokumentstruktur, Gliederung und Abschnittsreihenfolge (nicht deren Inhalt).
   > Stelle strukturierte Daten als Markdown-Tabellen dar. Erfinde keine Daten
   > oder Werte. Setze als Autorenzeile genau: „<author_names>". Setze als
   > Institutszeile genau: „<dateline>".

   CONTENT — override (only if a `PROMPT_OVERRIDE` was supplied): use the
   override text as CONTENT verbatim, then append this restated structure
   guarantee (the override may omit these, and the renderer + title block require
   them; if the samples decision was to ignore samples, drop the sample sentence
   as in Step 5):
   > Schreibe das Paper auf Deutsch, unabhängig von der Sprache der Quellen.
   > Stütze den Inhalt ausschließlich auf die bereitgestellten Quellen, deren
   > Titel NICHT mit "sample" beginnt; erfinde keine Daten oder Werte. Stelle
   > strukturierte Daten als Markdown-Tabellen dar. Setze als Autorenzeile genau:
   > "<author_names>". Setze als Institutszeile genau: "<dateline>". Falls
   > "sample*"-Quellen vorhanden sind, übernimm aus ihnen ausschließlich die
   > Dokumentstruktur, nicht deren Inhalt.

   Always append to the PROMPT (STRUCTURE — both modes):

   > Nenne den Abstract-Abschnitt exakt „Abstract" (englisches Wort, als
   > Überschrift „### Abstract"). Beende das Paper mit einem Abschnitt
   > „Literaturverzeichnis", der die tatsächlich verwendeten Quellen auflistet.

   If charts were requested, append to the PROMPT:

   > Wo der Bericht numerische Daten aus den Quellen zitiert, füge zusätzlich
   > einen Codeblock mit der Sprache „paperchart" ein (YAML: type: bar|line|pie;
   > title; labels: [...]; series: [- name, values: [...]]; bei pie genau eine
   > Serie; values müssen exakt den Zahlen aus den Quellen entsprechen — erfinde
   > keine Werte). Beispiel:
   >
   >     ```paperchart
   >     type: bar
   >     title: "Antwortzeiten"
   >     labels: ["10k", "100k"]
   >     series:
   >       - name: "p50"
   >         values: [12, 18]
   >     ```

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
     --authors "<AUTHOR_LINE>" --dateline "<dateline>" \
     --layout <one|two, as delegated> --charts <auto if charts requested, else off>
   ```
   This needs `pandoc`, `tectonic`, and `mmdc` on PATH (Tectonic fetches packages
   on first run — set the `HTTPS_PROXY`/`HTTP_PROXY` override per the network
   section, or its fetches DNS-fail behind the VPN). Handle the result:
   - Exit 0 (prints `Wrote …pdf`): the PDF is the primary deliverable.
   - Two-column failure: if `--layout two` was requested and the renderer fails,
     retry ONCE with `--layout one` (note the downgrade in your summary) before
     degrading to the Markdown-only outcome.
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
    otherwise the `.md`. Also report: how many charts the report contains
    (LLM-authored paperchart blocks vs auto-detected) and the layout actually
    used (two / downgraded-to-one / one), so the main agent can run the
    graphics review loop with the user.
