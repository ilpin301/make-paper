# make-paper v2.3 styling — design

Date: 2026-06-12. Four more user styling rules on top of v2.2, same layering:
`preprocess.py` = text transforms, `filters/paper_style.lua` = structure,
`templates/paper.latex` = looks, DOCX mirror in `build_reference_docx.py` /
`make_docx.py`. Reference look for tables: user-supplied `01.jpg` (centered
cells, full outer border, light-blue header row, small bold-label caption
tight under the table).

## Rule 1 — body text flush left; references full width

All text is left-aligned (ragged right) EXCEPT: main title (centered),
abstract (justified italic block, unchanged), formulas (centered equations,
unchanged), table cell content (centered, rule 4), and the
Literaturverzeichnis section (already flush-left one-liners since v2.2).

- Template: `\usepackage{ragged2e}`; `\RaggedRight` issued after the
  `\paperhead` call so the head/abstract keep their own alignment.
  `\RaggedRight` (not `\raggedright`) preserves `\parindent`.
- "Literaturverzeichnis like the abstract, one column": in the two-column
  layout the references section switches to full page width. The Lua filter
  inserts `\makeatletter\if@twocolumn\onecolumn\fi\makeatother` before the
  unnumbered Literaturverzeichnis header — layout-agnostic (no-op in
  one-column), no metadata plumbing. `\onecolumn` implies a page break;
  accepted trade-off (LaTeX cannot switch back to one column mid-page).
- DOCX: `BodyText`/`FirstParagraph` styles change from justified to left in
  `reference.docx`. In `--layout two`, `apply_two_column_layout` adds a
  second continuous section break before the "Literaturverzeichnis" Heading-1
  paragraph so references run single-column full width (no page break in
  Word — continuous breaks can rejoin columns mid-page).

## Rule 2 — no hyphenation; oversized tables span the page

- Template: `\hyphenpenalty=10000` + `\exhyphenpenalty=10000` (global, also
  inside tables); `\emergencystretch=3em` so the still-justified abstract
  doesn't overflow without hyphens.
- Lua filter: a table whose estimated content width exceeds `CHAR_BUDGET`
  (45 chars: sum over columns of the longest cell + ~3 chars padding each,
  ≈ what fits a two-column-layout column at `\small`) becomes a `table*`
  spanning the full page width — in addition to the existing ≥4-column rule.
  In one-column layout `table*` behaves like `table`, so the heuristic is
  harmless there.
- DOCX: Word does not hyphenate by default — nothing to do.

## Rule 3 — author/institution lines below the abstract are stripped

NotebookLM repeats author/institution data in prose-ish lines ("Autoren:
Petr N. (478314)…", "**Institution:** RWTH Aachen") that v2.1's exact-match
strip misses. Only the title block may carry this info.

- `preprocess.strip_author_lines` gains fuzzy matching, still restricted to
  the region before the first ATX heading: targets now include each
  author name with the matriculation number stripped and the institution
  (dateline up to the comma). A line is dropped when removing all matched
  targets leaves ≤ 24 letters (i.e. only a label like "Autoren:" /
  "Institution:" remains). Real sentences mentioning the institution keep
  their > 24 letters of own content and survive.
- `render()` additionally runs the same strip over the extracted abstract
  text, since such lines often sit inside the abstract section.
- DOCX: shared preprocess — applies automatically.

## Rule 4 — table look per 01.jpg

- Cells: all content centered H+V incl. the header row (already v2.1; kept).
- Borders: full outer border — colspecs gain outer `|…|` (the `@{}` edge
  suppression is dropped); booktabs `\toprule`/`\midrule`/`\bottomrule` are
  replaced by `\hline` so the verticals meet the horizontals cleanly
  (booktabs rules have different thickness and are documented not to mix
  with vlines).
- Header background: template loads `\usepackage[table]{xcolor}` and defines
  `tableheadbg` (RGB 217,226,243 — the 01.jpg light blue ≈ Word "Blue,
  Accent 1, Lighter 80%"); the filter injects `\rowcolor{tableheadbg}` after
  the top rule.
- Caption: stays below the table, `footnotesize` with bold "Tabelle N:"
  label (v2.1), now pulled closer via `\captionsetup[table]{skip=4pt}`.
- DOCX: `reference.docx` Table style gets the full border set (was insideV
  only) and the `TableCaption` style 8 pt; `make_docx.py` post-processes
  every table with python-docx direct formatting — header-row shading
  D9E2F3 and centered cell paragraphs (direct formatting because pandoc's
  `Compact` cell style would override table-style conditional formatting).

## Out of scope

- DOCX automatic table widening (rule 2): Word reflows tables itself.
- Caption text justification: caption package default kept.
