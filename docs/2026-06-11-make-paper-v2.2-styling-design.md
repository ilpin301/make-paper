# make-paper v2.2 — Paper Styling Rules (Design)

Date: 2026-06-11
Status: built (TDD, inline)
Builds on: `2026-06-11-make-paper-v2.1-styling-design.md` (8 rules, BUILT)

## The 4 rules and their mechanisms

1. **Abstract gets its heading back: "Abstract" in the general section-title
   style, but unnumbered.** (Revises v2.1 rule 2, which rendered the abstract
   label-free.) Template: `\section*{Abstract}` inside the `$if(abstract)$`
   block of `\paperhead`; the italic 2em-indented abstract text below is
   unchanged. Works inside `\twocolumn[{...}]`, so the heading spans both
   columns in two-column layout like the rest of the head.

2. **Dot after first-level section numbers only ("1. Einleitung", but
   "1.1 Motivation").** Template:
   `\renewcommand{\thesection}{\arabic{section}.}` plus an explicit
   `\renewcommand{\thesubsection}{\arabic{section}.\arabic{subsection}}` —
   restated without `\thesection` so subsections don't inherit the dot and
   become "1..1". `\thesubsubsection` builds on `\thesubsection` and needs no
   change.

3. **Every Literaturverzeichnis entry starts on its own line.** Preprocess
   `move_references_last`: entries are now joined with pandoc hard line
   breaks (trailing backslash) instead of soft-flowing lines — one paragraph,
   one line per entry, all flush left (no paragraph indent on entries 2+,
   which blank-line separation would have caused).

4. **Vertical lines between table columns (none at the outer edges).**
   `paper_style.lua`: after the longtable→tabular conversion, insert `|`
   between column specs — simple colspecs arrive as one `c` run
   (`{@{}cc@{}}` → `{@{}c|c@{}}`); width-managed ones as one
   `>{...}m{... \real{x.xxxx}}` line per column (insert `|` between
   consecutive lines). Template support: `\aboverulesep`/`\belowrulesep` set
   to 0pt so the booktabs rules meet the vertical lines without gaps, with
   `\arraystretch` 1.15 restoring the row breathing room.

## Testing

89/89 (2 net-new tests; 3 existing tests extended):
- `test_move_references_entries_each_start_a_new_line` (preprocess)
- `test_template_has_v22_styling_declarations` (template strings)
- `test_paper_style_filter_tables_and_equations` now asserts `c|c` colspecs
  and the width-managed separator (real pandoc)
- `test_template_compiles_both_layouts_with_styling` now extracts PDF text
  and asserts "Abstract" present, "1..1" absent, "1.1" intact

Acceptance: `F:\____IL_AI\test\Papers\Test Paper v2.2.pdf` (two-column)
verified rule-by-rule via pymupdf — "Abstract" at 14.3pt bold matching
numbered headings, dotted first-level numbers, per-line `[n]` entries at
distinct y-positions, vertical line segments present on table pages.
