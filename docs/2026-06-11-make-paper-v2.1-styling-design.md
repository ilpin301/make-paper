# make-paper v2.1 — Paper Styling Rules (Design)

Date: 2026-06-11
Status: approved by user (brainstorming session)
Builds on: `2026-06-11-make-paper-v2-design.md` (charts + two-column, BUILT)

## Goal

Eight user-specified styling rules so rendered papers match the Di04 sample's
conventions (with explicit user overrides where the user differs from the
sample). All changes live in Subsystem B plus two prompt lines in the agent.

Facts measured from the sample (`Di04_SPE_Nasybulin_Gembruch.pdf` via pymupdf):
figure captions are 8 pt with a **bold** "Abbildung N:" label and regular
caption text; body is 10 pt Times. The sample's abstract/references are plain,
but the USER explicitly wants both in italics — user choice wins.

## The 8 rules and their mechanisms

1. **Abstract is named "Abstract" (English), never "Zusammenfassung".**
   - Agent Step-6 prompt: instruct NotebookLM to title the section exactly
     `### Abstract`.
   - `extract_abstract` already recognizes abstract/zusammenfassung/kurzfassung
     and absorbs the heading, so German titles in old reports still work.
   - No abstract label is ever rendered in the PDF (rule 2).

2. **Abstract rendering: full page width (even in two-column), indented ~2em
   from both margins, italic, NO heading.**
   - Template, two-column case: replace plain `\maketitle` + `abstract` env
     with `\twocolumn[{<centered title + authors + dateline> <italic indented
     abstract>}]` so the head spans both columns.
   - Single-column case: `\maketitle` + the same italic indented block (list
     environment with 2em margins), no `abstract` environment, no label.

3. **Authors + dateline appear ONLY at the title block (below the title, as in
   the sample).**
   - New preprocess step `strip_author_lines(md, authors, dateline)`: in the
     region before the abstract/first heading, drop lines whose content
     (after removing `*`/`_` emphasis markers and collapsing whitespace)
     equals the authors line or the dateline. Exact-match only; absent → no-op.
   - Renderer passes its `--authors`/`--dateline` values in.

4. **"Literaturverzeichnis" is always the last section; entries numbered
   `[1]`, `[2]`, …; text italic (same style as abstract).**
   - New preprocess step `move_references_last(md)`: find a section titled
     Literaturverzeichnis/Literatur/Quellen/Referenzen (any heading level);
     retitle to `Literaturverzeichnis`; move section to document end; convert
     entries (`1.` ordered, `-`/`*` bulleted, or bare non-empty lines) to
     `*[n] <text>*` (Markdown italics). Absent section → no-op.
   - Agent Step-6 prompt: request a closing Literaturverzeichnis section
     listing the actual sources used.

5. **Display formulas numbered `(1)`, `(2)`, … at end of line.**
   - `paper_style.lua`: map every DisplayMath element to a raw LaTeX
     `\begin{equation} … \end{equation}` block (article class numbers them
     `(n)` right-aligned). Inline math untouched.

6. **Table cell content centered horizontally AND vertically.**
   - `paper_style.lua` absorbs and replaces `twocolumn_tables.lua`, and is
     applied in BOTH layouts: every table becomes a float (`table`, or
     `table*` at ≥4 columns — harmless in single-column) built from the
     longtable→tabular conversion already proven in v2, with all colspecs
     forced to AlignCenter before writing and `p{...}` column specs rewritten
     to `>{\centering\arraybackslash}m{...}` (m-columns vertically center).
   - `--layout two` now contributes only `-V classoption=twocolumn`;
     `paper_style.lua` is passed unconditionally. `twocolumn_tables.lua` is
     deleted (its tests migrate to the new filter).
   - Accepted trade-off: floats don't break across pages; paper tables are
     short.

7. **Every graph gets a caption below it: "Abbildung N: <title>" styled like
   the sample (small, bold label).**
   - `render_paperchart_blocks` / `inject_autodetected_charts` emit
     `![<spec.title>](<figure>.pdf)` (alt text = caption); pandoc's implicit
     figures produce `\begin{figure}` + `\caption`; polyglossia German yields
     the "Abbildung N:" prefix.
   - `render_chart` no longer draws `spec.title` inside the image (the
     caption replaces it; axis labels/legend stay).
   - Template: `\usepackage{caption}` +
     `\captionsetup{font=footnotesize,labelfont=bf,labelsep=colon}`.
   - Mermaid blocks keep empty alt (no caption) — unchanged, none in current
     reports.

8. **Section numbering 1 / 1.1 / 1.1.1 …**
   - New preprocess step `promote_headings(md)`: after title/abstract
     extraction, find the minimum ATX heading level in the body and shift all
     headings up uniformly so that minimum becomes level 1 (H3→H1 etc.).
     Pandoc then maps them to section/subsection/subsubsection and
     `--number-sections` numbers them 1 / 1.1 / 1.1.1. Already-level-1 body →
     no-op. (NotebookLM emits H3/H4 today, which currently produces broken
     0.0.x numbering — this fixes that bug too.)

## Pipeline order (render())

strip_heading_numbers → extract_title → extract_abstract →
**strip_author_lines** → **move_references_last** → **promote_headings** →
resolve_images → paperchart/autodetect (now with alt-text captions) →
mermaid → frontmatter → pandoc (`--lua-filter paper_style.lua` always,
`-V classoption=twocolumn` if two) → Tectonic.

## Error handling

Every new preprocess step no-ops cleanly when its target is absent. The
author-line strip matches exact content only (never deletes prose). The Lua
filter touches only Table and DisplayMath elements. No new hard dependencies;
no new CLI flags; subagent protocol unchanged except two prompt lines.

## Testing

- Unit: each new preprocess function — hit and no-op cases, emphasis-marker
  tolerance (authors), entry-format variants (references), uniform shift
  including H4-under-H3 (headings).
- Integration (real pandoc): `paper_style.lua` on fixture md asserting
  `\begin{equation}`, no `\[`, centered `m{}`/`c` colspecs, `table*` for wide,
  `\caption{` for captioned image, no `longtable`.
- Regression: both-layout template compiles; full suite stays green.
- Acceptance: re-render `F:\____IL_AI\test\Papers\Test Paper v2.md` two-column
  and verify all 8 rules in one PDF.

## Out of scope

- Unnumbered-equation opt-out, caption styling knobs, mermaid captions,
  bibliography management (BibTeX) — only if requested later. The user
  expects future styling additions; this file is the precedent for how they
  land (preprocess = text, paper_style.lua = structure, template = looks).
