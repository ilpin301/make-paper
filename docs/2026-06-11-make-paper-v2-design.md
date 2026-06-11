# make-paper v2 — Auto-Charts + Two-Column Layout (Design)

Date: 2026-06-11
Status: approved by user (brainstorming session)
Builds on: `2026-06-10-make-paper-design.md`, `2026-06-10-make-paper-subsystem-b-plan.md` ("Deferred to v2")

## Goal

Add the two features deferred from v1, entirely inside Subsystem B plus a
prompt/protocol update to the subagent:

1. **Data charts** — vector figures generated from numeric data that already
   exists in the Wiki sources (CLEAR "never invent" rule). Two producers:
   LLM-authored chart blocks (primary) and renderer auto-detection (fallback).
2. **Two-column layout** — per-run choice, faithful to the academic sample,
   via `article` class `twocolumn` option + a pandoc Lua filter that converts
   tables to floats (approach A; IEEEtran and multicol rejected).

User-visible additions: the main session asks two new pre-run questions
(layout, charts) and runs a post-run **chart review loop** (add/remove/change
charts, local re-render only).

## Decisions (locked)

- Chart source: **both** — LLM-authored ```` ```paperchart ```` blocks primary;
  auto-detect from numeric Markdown tables ONLY when the model emitted zero
  blocks (fallback, not additive).
- Chart tech: **matplotlib** rendering a small YAML spec to **vector PDF**
  figures sized to one column width, fonts matched to the paper (Times-like).
  Mermaid xychart rejected (beta, no pie, weak styling).
- Two-column: **per-run choice** `--layout one|two`, default `one`
  (back-compat; single-column output stays byte-identical to v1). Approach A:
  `classoption: twocolumn` + Lua filter `longtable → tabular` in `table`
  (narrow) / `table*` (wide, heuristic: ≥4 columns) floats.
- Interaction: the subagent cannot ask the user anything; pre-run questions
  and the post-run chart review loop are MAIN-session responsibilities,
  codified in the agent description.

## The `paperchart` spec

Fenced block, YAML body:

```paperchart
type: bar            # bar | line | pie
title: "Antwortzeiten nach Indexgröße"
xlabel: "Indexgröße"  # optional; ignored for pie
ylabel: "ms"          # optional; ignored for pie
labels: ["10k", "100k", "1M"]
series:
  - name: "p50"
    values: [12, 18, 35]
  - name: "p99"      # pie: exactly one series
    values: [40, 95, 210]
```

Validation: known `type`; `labels` non-empty; every `series[].values` same
length as `labels`; values numeric. Invalid → skip chart, warn, continue.

## Components

### 1. `render/charts.py` (new)

- `parse_paperchart(code: str) -> ChartSpec` — parse + validate YAML into a
  dataclass; raise `ChartSpecError` with a human message on any violation.
- `render_chart(spec, out_path: Path) -> None` — matplotlib, Agg backend,
  vector PDF, single-column width (~3.35in), serif fonts, no chartjunk
  (no gridline noise, thin spines), series legend only when >1 series.
- `autodetect_charts(md: str) -> list[AutoChart]` — scan Markdown pipe tables;
  a table is chartable when: first column = labels (non-numeric), ≥1 fully
  numeric column (after stripping units/`%`/thousands separators), ≥3 data
  rows, ≤12 rows. Chart type: `line` if labels are year-like/numeric and ≥4
  rows, else `bar`. Title from preceding table caption/heading context if
  available, else column header. Returns spec + the table's position so the
  figure can be injected after it.

Dependency policy: matplotlib + pyyaml imported lazily inside `charts.py`;
if import fails, chart rendering is skipped with a warning naming the
`pip install` fix. They do NOT join `REQUIRED_TOOLS`.

### 2. `render/preprocess.py` (additions)

- `render_paperchart_blocks(md, out_dir, renderer) -> tuple[str, int]` —
  replace each valid ```paperchart block with `![](figure.pdf)` (same
  hash-named pattern as the Mermaid path); returns count of blocks found
  (valid or not) so the pipeline knows whether the fallback applies.
- `inject_autodetected_charts(md, out_dir, renderer) -> str` — run only when
  charts are enabled AND zero paperchart blocks were found; insert the figure
  link after each chartable table.

### 3. `render/filters/twocolumn_tables.lua` (new)

Pandoc Lua filter, applied only with `--layout two`. For each `Table`
element: emit raw LaTeX — `tabular` (booktabs rules) wrapped in `table`
(< 4 columns) or `table*` (≥ 4 columns), `[t]` placement, caption preserved.
Rationale: pandoc's `longtable` output errors inside LaTeX `twocolumn`.

### 4. `render/templates/paper.latex` (edit)

Add `$if(classoption)$` to `\documentclass[...]`; everything else unchanged.
With `--layout one` no variable is set and output is identical to v1.

### 5. `render/render_paper.py` (edits)

- CLI: `--layout {one,two}` default `one`; `--charts {auto,blocks,off}`
  default `blocks` (`auto` = blocks + fallback autodetect; `blocks` = only
  LLM-authored; `off` = strip paperchart blocks, no figures).
- `build_pandoc_cmd` gains the Lua filter + `-V classoption=twocolumn` when
  layout is `two`.
- Pipeline order: existing transforms → paperchart blocks → autodetect
  fallback (`auto` only) → Mermaid → frontmatter → pandoc → Tectonic.

### 6. `agents/make-paper.md` (edits)

- Description/precondition: main agent asks FOUR things pre-run: profile,
  notebook name, **layout** (one/two), **charts** (yes→`auto` / no→`off`).
- Step 6 prompt addition (German): where the report cites numeric data from
  the sources, also emit a ```paperchart block (spec shown inline); charts
  may only visualize numbers present in the sources; never invent values.
- Step 8: pass `--layout`/`--charts`; on a two-column render failure retry
  once with `--layout one` before degrading to Markdown-only.
- Return contract: instruct the main agent to open the PDF and ask the user
  what to change in the graphics (remove/add/retype charts); apply by editing
  paperchart blocks in `Papers/<name>.md` and re-running the renderer
  (local loop, no NotebookLM round trip), repeating until satisfied.

## Error handling

| Failure | Behavior |
|---|---|
| Malformed paperchart YAML / validation error | Skip that chart, warn with block excerpt, continue |
| matplotlib/pyyaml not importable | Skip all charts, warn with install hint, continue |
| Chart render exception | Same as malformed: skip, warn, continue |
| Two-column pandoc/Tectonic failure | Subagent retries `--layout one`, then degrades to `.md` |
| Autodetect finds nothing | Normal outcome, noted in summary |

## Testing

TDD throughout, mirroring v1's test layout.

- Unit (`tests/test_charts.py`): spec parsing valid/invalid (unknown type,
  length mismatch, non-numeric), autodetect heuristics on fixture tables
  (chartable bar, year-line, non-chartable text table, too-short table),
  type selection, unit/percent stripping.
- Unit (`tests/test_preprocess.py` additions): paperchart block → figure
  link substitution + count, invalid block skipped in place, autodetect
  injection position, `--charts off` stripping.
- Unit (`tests/test_render_paper.py` additions): CLI flag wiring, pandoc
  argv with/without Lua filter + classoption, fallback-trigger logic.
- Integration (real toolchain): Lua filter through real pandoc on fixture
  tables asserting `table*`/`tabular`/absence of `longtable`; one real
  matplotlib chart PDF produced.
- End-to-end acceptance: re-render the real `CLEAR Paper.md` with
  `--layout two --charts auto` → two-column PDF, ≥1 auto-detected chart,
  no NotebookLM needed.

## Out of scope

- NotebookLM-side native charts (CLI doesn't expose them; tracked in
  notebooklm-cli-facts memory as a watch item).
- Scatter/stacked/multi-axis chart types; balance-column tweaking; abstract
  spanning both columns (stays in first column).
