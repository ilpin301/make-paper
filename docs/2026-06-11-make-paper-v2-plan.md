# make-paper v2 Implementation Plan — Auto-Charts + Two-Column

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `paperchart` data charts (LLM-authored + auto-detect fallback, matplotlib) and a per-run two-column layout (`--layout two`, Lua filter for tables) to Subsystem B, plus the subagent protocol updates.

**Architecture:** New `render/charts.py` (spec parsing, matplotlib rendering, table auto-detection) feeds two new `preprocess.py` transforms; a pandoc Lua filter (`render/filters/twocolumn_tables.lua`) converts tables to `table`/`table*` floats so `twocolumn` survives; `render_paper.py` grows `--layout`/`--charts` flags. Spec: `docs/2026-06-11-make-paper-v2-design.md`.

**Tech Stack:** Python 3.14, pytest, PyYAML + matplotlib (lazy imports, soft dependency), pandoc Lua filter, Tectonic.

**Working directory for all commands:** `C:\Users\il720506\.claude\make-paper` (its own git repo). All `git`/`pytest` commands run there. NOTE: do not run git with forward-slash absolute paths while CLEAR is the active project (pollutes CLEAR's settings allow-list).

**Repo layout touched:**

```
render/
  charts.py                     # NEW: ChartSpec, parse_paperchart, render_chart, autodetect_charts
  preprocess.py                 # MODIFY: + render_paperchart_blocks, inject_autodetected_charts
  render_paper.py               # MODIFY: --layout/--charts, run_paperchart, pipeline wiring
  filters/twocolumn_tables.lua  # NEW: longtable → table/table* floats
  templates/paper.latex         # MODIFY: classoption variable + columnsep
tests/
  test_charts.py                # NEW
  test_preprocess.py            # MODIFY: + paperchart/inject tests
  test_render_paper.py          # MODIFY: + flag/pipeline/Lua-filter tests
agents/make-paper.md            # MODIFY: preconditions, prompt, flags, retry, review loop
```

---

### Task 1: Dependencies + `parse_paperchart`

**Files:**
- Create: `render/charts.py`
- Create: `tests/test_charts.py`

- [ ] **Step 1: Install soft dependencies**

Run: `python -m pip install pyyaml matplotlib`
Expected: `Successfully installed ...` (or already satisfied). These are soft deps — `charts.py` imports them lazily; the renderer must keep working without them (Task 6 wires the skip).

- [ ] **Step 2: Write failing tests for spec parsing**

Create `tests/test_charts.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))

import charts


VALID = """\
type: bar
title: "Antwortzeiten nach Indexgröße"
xlabel: "Indexgröße"
ylabel: "ms"
labels: ["10k", "100k", "1M"]
series:
  - name: "p50"
    values: [12, 18, 35]
  - name: "p99"
    values: [40, 95, 210]
"""


def test_parse_valid_bar_spec():
    spec = charts.parse_paperchart(VALID)
    assert spec.type == "bar"
    assert spec.title == "Antwortzeiten nach Indexgröße"
    assert spec.xlabel == "Indexgröße" and spec.ylabel == "ms"
    assert spec.labels == ["10k", "100k", "1M"]
    assert [s.name for s in spec.series] == ["p50", "p99"]
    assert spec.series[1].values == [40.0, 95.0, 210.0]


def test_parse_minimal_line_spec_defaults():
    spec = charts.parse_paperchart(
        "type: line\nlabels: [2019, 2020, 2021]\nseries:\n  - values: [1, 2, 3]\n"
    )
    assert spec.type == "line"
    assert spec.labels == ["2019", "2020", "2021"]  # coerced to str
    assert spec.title == "" and spec.xlabel == "" and spec.ylabel == ""
    assert spec.series[0].name == ""


@pytest.mark.parametrize("code,msg", [
    ("not: [valid", "invalid YAML"),
    ("- just\n- a list\n", "mapping"),
    ("type: radar\nlabels: [a]\nseries: [{values: [1]}]\n", "unknown type"),
    ("type: bar\nlabels: []\nseries: [{values: []}]\n", "labels"),
    ("type: bar\nlabels: [a, b]\nseries: []\n", "series"),
    ("type: bar\nlabels: [a, b]\nseries: [{values: [1]}]\n", "length"),
    ("type: bar\nlabels: [a, b]\nseries: [{values: [1, zwei]}]\n", "numbers"),
    ("type: pie\nlabels: [a, b]\nseries: [{values: [1, 2]}, {values: [3, 4]}]\n", "pie"),
])
def test_parse_rejects_bad_specs(code, msg):
    with pytest.raises(charts.ChartSpecError) as exc:
        charts.parse_paperchart(code)
    assert msg.lower() in str(exc.value).lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_charts.py -q`
Expected: collection error / failures — `ModuleNotFoundError: No module named 'charts'`.

- [ ] **Step 4: Implement `ChartSpec` + `parse_paperchart`**

Create `render/charts.py`:

```python
"""paperchart spec parsing, matplotlib rendering, and table auto-detection
for make-paper Subsystem B v2. PyYAML and matplotlib are imported lazily so
the rest of the renderer works without them."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class ChartSpecError(ValueError):
    """A paperchart block is malformed; the chart is skipped, never fatal."""


@dataclass
class Series:
    name: str
    values: list[float]


@dataclass
class ChartSpec:
    type: str
    labels: list[str]
    series: list[Series]
    title: str = ""
    xlabel: str = ""
    ylabel: str = ""


def parse_paperchart(code: str) -> ChartSpec:
    """Parse + validate a ```paperchart YAML body into a ChartSpec."""
    import yaml

    try:
        data = yaml.safe_load(code)
    except yaml.YAMLError as e:
        raise ChartSpecError(f"invalid YAML: {e}")
    if not isinstance(data, dict):
        raise ChartSpecError("spec must be a YAML mapping")
    ctype = data.get("type")
    if ctype not in ("bar", "line", "pie"):
        raise ChartSpecError(f"unknown type: {ctype!r} (want bar|line|pie)")
    labels = data.get("labels")
    if not isinstance(labels, list) or not labels:
        raise ChartSpecError("labels must be a non-empty list")
    labels = [str(x) for x in labels]
    raw_series = data.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise ChartSpecError("series must be a non-empty list")
    series: list[Series] = []
    for s in raw_series:
        if not isinstance(s, dict) or "values" not in s:
            raise ChartSpecError("each series needs a values list")
        vals = s["values"]
        if not isinstance(vals, list) or len(vals) != len(labels):
            raise ChartSpecError("series values length must match labels length")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            raise ChartSpecError("series values must be numbers")
        series.append(Series(name=str(s.get("name", "")), values=[float(v) for v in vals]))
    if ctype == "pie" and len(series) != 1:
        raise ChartSpecError("pie needs exactly one series")
    return ChartSpec(
        type=ctype, labels=labels, series=series,
        title=str(data.get("title", "")),
        xlabel=str(data.get("xlabel", "")),
        ylabel=str(data.get("ylabel", "")),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_charts.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add render/charts.py tests/test_charts.py
git commit -m "feat(v2): paperchart spec parsing with validation"
```

---

### Task 2: `render_chart` (matplotlib)

**Files:**
- Modify: `render/charts.py` (append)
- Modify: `tests/test_charts.py` (append)

- [ ] **Step 1: Write failing tests (real matplotlib, all three types)**

Append to `tests/test_charts.py`:

```python
def _have_chart_deps():
    try:
        import matplotlib  # noqa: F401
        import yaml  # noqa: F401
        return True
    except ImportError:
        return False


needs_deps = pytest.mark.skipif(not _have_chart_deps(), reason="matplotlib/yaml not installed")


@needs_deps
@pytest.mark.parametrize("ctype,series", [
    ("bar", [{"name": "p50", "values": [1, 2, 3]}, {"name": "p99", "values": [4, 5, 6]}]),
    ("line", [{"name": "A", "values": [1, 2, 3]}]),
    ("pie", [{"values": [30, 50, 20]}]),
])
def test_render_chart_writes_vector_pdf(tmp_path, ctype, series):
    spec = charts.ChartSpec(
        type=ctype, labels=["a", "b", "c"],
        series=[charts.Series(s.get("name", ""), [float(v) for v in s["values"]]) for s in series],
        title="Testdiagramm", xlabel="x", ylabel="y",
    )
    out = tmp_path / f"{ctype}.pdf"
    charts.render_chart(spec, out)
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 1000


def test_charts_available_reports_or_none():
    msg = charts.charts_available()
    assert msg is None or "pip install" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_charts.py -q`
Expected: new tests FAIL with `AttributeError: ... 'render_chart'`.

- [ ] **Step 3: Implement `render_chart` + `charts_available`**

Append to `render/charts.py`:

```python
def charts_available() -> str | None:
    """None if chart deps import; else a warning with the install fix."""
    try:
        import matplotlib  # noqa: F401
        import yaml  # noqa: F401
        return None
    except ImportError as e:
        return f"charts skipped ({e.name} not installed — pip install pyyaml matplotlib)"


def render_chart(spec: ChartSpec, out_path) -> None:
    """Render a ChartSpec to a vector PDF sized for one paper column."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "font.size": 8})
    fig, ax = plt.subplots(figsize=(3.35, 2.4))
    pos = range(len(spec.labels))
    if spec.type == "pie":
        ax.pie(spec.series[0].values, labels=spec.labels,
               autopct="%1.0f%%", textprops={"fontsize": 8})
    elif spec.type == "line":
        for s in spec.series:
            ax.plot(list(pos), s.values, marker="o", linewidth=1.2,
                    markersize=3, label=s.name)
        ax.set_xticks(list(pos))
        ax.set_xticklabels(spec.labels)
    else:  # bar
        width = 0.8 / len(spec.series)
        for i, s in enumerate(spec.series):
            ax.bar([x + i * width for x in pos], s.values, width, label=s.name)
        ax.set_xticks([x + 0.4 - width / 2 for x in pos])
        ax.set_xticklabels(spec.labels)
    if spec.type != "pie":
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if spec.xlabel:
            ax.set_xlabel(spec.xlabel)
        if spec.ylabel:
            ax.set_ylabel(spec.ylabel)
        if len(spec.series) > 1 and any(s.name for s in spec.series):
            ax.legend(frameon=False)
    if spec.title:
        ax.set_title(spec.title)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_charts.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add render/charts.py tests/test_charts.py
git commit -m "feat(v2): matplotlib chart rendering (bar/line/pie, vector PDF)"
```

---

### Task 3: Number parsing + `autodetect_charts`

**Files:**
- Modify: `render/charts.py` (append)
- Modify: `tests/test_charts.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_charts.py`:

```python
@pytest.mark.parametrize("cell,expected", [
    ("42", 42.0),
    ("-3.5", -3.5),
    ("1,234", 1234.0),        # single comma + 3 digits = thousands
    ("3,5", 3.5),             # German decimal comma
    ("1.234.567", 1234567.0), # German thousands dots... rejected? see impl: both seps absent
    ("12 ms", 12.0),          # trailing unit allowed
    ("85%", 85.0),
    ("ca. 12", None),         # leading text → not a clean number cell
    ("schnell", None),
    ("", None),
])
def test_to_number(cell, expected):
    assert charts._to_number(cell) == expected


CHARTABLE = """\
## Latenzmessungen

| Indexgröße | p50 | p99 |
|---|---|---|
| 10k | 12 | 40 |
| 100k | 18 | 95 |
| 1M | 35 | 210 |
"""

YEARLY = """\
| Jahr | Nutzer |
|---|---|
| 2019 | 100 |
| 2020 | 250 |
| 2021 | 600 |
| 2022 | 900 |
"""

TEXT_TABLE = """\
| Komponente | Zweck |
|---|---|
| Wiki | Notizen |
| Schema | Struktur |
| Skripte | Automatisierung |
"""

TOO_SHORT = """\
| A | B |
|---|---|
| x | 1 |
| y | 2 |
"""


def test_autodetect_finds_bar_chart_with_heading_title():
    found = charts.autodetect_charts(CHARTABLE)
    assert len(found) == 1
    spec, end_line = found[0]
    assert spec.type == "bar"
    assert spec.title == "Latenzmessungen"          # from preceding heading
    assert spec.labels == ["10k", "100k", "1M"]
    assert [s.name for s in spec.series] == ["p50", "p99"]
    assert spec.xlabel == "Indexgröße"
    assert CHARTABLE.splitlines()[end_line].startswith("| 1M")


def test_autodetect_year_labels_make_line_chart():
    found = charts.autodetect_charts(YEARLY)
    assert len(found) == 1
    spec, _ = found[0]
    assert spec.type == "line"
    assert spec.ylabel == "Nutzer"                  # single series → ylabel from header


def test_autodetect_skips_text_and_short_tables():
    assert charts.autodetect_charts(TEXT_TABLE) == []
    assert charts.autodetect_charts(TOO_SHORT) == []


def test_autodetect_multiple_tables_keeps_order():
    md = CHARTABLE + "\nZwischentext.\n\n" + YEARLY
    found = charts.autodetect_charts(md)
    assert [spec.type for spec, _ in found] == ["bar", "line"]
```

NOTE on `1.234.567`: the `_to_number` below treats a dot-only token with multiple dots as invalid float → returns `None`... but the test above expects `1234567.0`. The implementation handles it: multiple dots and no comma → dots are thousands separators when every group after the first has 3 digits.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_charts.py -q`
Expected: FAIL — `AttributeError: ... '_to_number'`.

- [ ] **Step 3: Implement number parsing + auto-detection**

Append to `render/charts.py`:

```python
_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_SEP = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_NUMCELL = re.compile(r"^\s*[-+]?\d[\d.,]*\s*(?:%|[A-Za-zµ°/²³]{1,6})?\s*$")
_YEAR = re.compile(r"^\d{4}$")
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.*\S)\s*$")


def _to_number(cell: str) -> float | None:
    """Parse a table cell into a float; tolerate units/% and de/en separators."""
    if not _NUMCELL.match(cell):
        return None
    tok = re.match(r"\s*[-+]?[\d.,]+", cell).group(0).strip().rstrip(".,")
    if "." in tok and "," in tok:
        if tok.rfind(",") > tok.rfind("."):
            tok = tok.replace(".", "").replace(",", ".")   # 1.234,5 → 1234.5
        else:
            tok = tok.replace(",", "")                     # 1,234.5 → 1234.5
    elif tok.count(",") == 1:
        head, tail = tok.split(",")
        tok = head + tail if len(tail) == 3 else head + "." + tail
    elif "," in tok:
        tok = tok.replace(",", "")
    elif tok.count(".") > 1:
        groups = tok.split(".")
        if all(len(g) == 3 for g in groups[1:]):
            tok = "".join(groups)                          # 1.234.567 → 1234567
        else:
            return None
    try:
        return float(tok)
    except ValueError:
        return None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _context_title(lines: list[str], table_start: int) -> str | None:
    """Nearest preceding non-blank line, if it is a heading."""
    for k in range(table_start - 1, max(-1, table_start - 4), -1):
        text = lines[k].strip()
        if not text:
            continue
        m = _HEADING_LINE.match(text)
        return m.group(1) if m else None
    return None


def _table_to_spec(header, rows, lines, table_start) -> ChartSpec | None:
    rows = [r for r in rows if len(r) == len(header)]
    if not (3 <= len(rows) <= 12) or len(header) < 2:
        return None
    labels = [r[0] for r in rows]
    labels_numeric = all(_to_number(x) is not None for x in labels)
    labels_yearlike = all(_YEAR.match(x) for x in labels)
    if labels_numeric and not labels_yearlike:
        return None  # first column must be label-like (years are OK)
    numeric_cols = []
    for c in range(1, len(header)):
        vals = [_to_number(r[c]) for r in rows]
        if all(v is not None for v in vals):
            numeric_cols.append((header[c], vals))
    if not numeric_cols:
        return None
    ctype = "line" if labels_yearlike and len(rows) >= 4 else "bar"
    title = _context_title(lines, table_start) or numeric_cols[0][0]
    return ChartSpec(
        type=ctype, labels=labels,
        series=[Series(name=n, values=v) for n, v in numeric_cols],
        title=title, xlabel=header[0],
        ylabel=numeric_cols[0][0] if len(numeric_cols) == 1 else "",
    )


def autodetect_charts(md: str) -> list[tuple[ChartSpec, int]]:
    """Find chartable Markdown pipe tables.

    Returns (spec, last_line_index) per table, in document order.
    """
    lines = md.splitlines()
    out: list[tuple[ChartSpec, int]] = []
    i = 0
    while i < len(lines):
        if _ROW.match(lines[i]) and i + 1 < len(lines) and _SEP.match(lines[i + 1]):
            header = _cells(lines[i])
            j = i + 2
            rows = []
            while j < len(lines) and _ROW.match(lines[j]) and not _SEP.match(lines[j]):
                rows.append(_cells(lines[j]))
                j += 1
            spec = _table_to_spec(header, rows, lines, i)
            if spec:
                out.append((spec, j - 1))
            i = j
        else:
            i += 1
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_charts.py -q`
Expected: all PASS. If `test_to_number[1.234.567]` fails, the multi-dot branch is wrong — fix the branch, not the test.

- [ ] **Step 5: Commit**

```bash
git add render/charts.py tests/test_charts.py
git commit -m "feat(v2): chartable-table auto-detection with de/en number parsing"
```

---

### Task 4: preprocess — `render_paperchart_blocks` + `inject_autodetected_charts`

**Files:**
- Modify: `render/preprocess.py` (append)
- Modify: `tests/test_preprocess.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_preprocess.py`:

```python
PAPERCHART_MD = (
    "Vorher.\n\n"
    "```paperchart\ntype: bar\nlabels: [a]\nseries: [{values: [1]}]\n```\n\n"
    "Nachher.\n"
)


def test_render_paperchart_blocks_replaces_with_figure(tmp_path):
    def runner(code, out_path):
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out, count = pre.render_paperchart_blocks(PAPERCHART_MD, tmp_path, runner)
    assert count == 1
    assert "```paperchart" not in out
    assert "![](" in out and ".pdf)" in out
    assert "Vorher." in out and "Nachher." in out


def test_render_paperchart_blocks_drops_failed_block(tmp_path):
    out, count = pre.render_paperchart_blocks(
        PAPERCHART_MD, tmp_path, lambda code, out_path: None
    )
    assert count == 1
    assert "```paperchart" not in out
    assert "![](" not in out


def test_render_paperchart_blocks_counts_all_blocks(tmp_path):
    md = PAPERCHART_MD + "\n```paperchart\nkaputt: [\n```\n"
    out, count = pre.render_paperchart_blocks(md, tmp_path, lambda c, p: None)
    assert count == 2


def test_inject_autodetected_charts_inserts_after_table(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n\nDanach.\n"
    fake_spec = object()

    def detect(text):
        return [(fake_spec, 4)]  # last table line index

    def runner(spec, out_path):
        assert spec is fake_spec
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out = pre.inject_autodetected_charts(md, tmp_path, runner, detect)
    lines = out.splitlines()
    fig_idx = next(i for i, l in enumerate(lines) if l.startswith("![]("))
    assert fig_idx > 4
    assert lines.index("Danach.") > fig_idx


def test_inject_autodetected_charts_skips_failed_renders(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n"
    out = pre.inject_autodetected_charts(
        md, tmp_path, lambda spec, p: None, lambda text: [(object(), 4)]
    )
    assert "![](" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_preprocess.py -q -k paperchart`
Expected: FAIL — `AttributeError: module 'preprocess' has no attribute 'render_paperchart_blocks'`.

- [ ] **Step 3: Implement both transforms**

Append to `render/preprocess.py`:

```python
_PAPERCHART = re.compile(r"^```paperchart[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)


def render_paperchart_blocks(md: str, out_dir: Path, runner) -> tuple[str, int]:
    """Replace each ```paperchart block via `runner(code, out_path) -> path|None`.

    None (parse/render failure) drops the block from the document. Returns
    (rewritten_md, total_blocks_found) — the count includes failed blocks so
    the caller can decide whether the auto-detect fallback applies.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        count += 1
        code = m.group(1)
        digest = hashlib.sha1(code.encode("utf-8")).hexdigest()[:12]
        result = runner(code, out_dir / f"chart-{digest}.pdf")
        return f"![]({Path(result).as_posix()})" if result else ""

    return _PAPERCHART.sub(repl, md), count


def inject_autodetected_charts(md: str, out_dir: Path, runner, detect) -> str:
    """Insert auto-detected chart figures after their source tables.

    `detect(md)` yields (spec, last_table_line_index); `runner(spec, out_path)`
    returns the figure path or None (skip). Insertions go bottom-up so earlier
    indices stay valid.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = md.splitlines()
    found = detect(md)
    for n, (spec, end_idx) in zip(range(len(found), 0, -1), reversed(found)):
        result = runner(spec, out_dir / f"autochart-{n:02d}.pdf")
        if result:
            lines[end_idx + 1:end_idx + 1] = ["", f"![]({Path(result).as_posix()})"]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_preprocess.py -q`
Expected: all PASS (old tests too).

- [ ] **Step 5: Commit**

```bash
git add render/preprocess.py tests/test_preprocess.py
git commit -m "feat(v2): paperchart block substitution + autodetect injection transforms"
```

---

### Task 5: Lua filter + template `classoption`

**Files:**
- Create: `render/filters/twocolumn_tables.lua`
- Modify: `render/templates/paper.latex:1` (documentclass line) and after line 20 (`\usepackage{calc}...`)
- Modify: `tests/test_render_paper.py` (append)

- [ ] **Step 1: Write failing integration tests (real pandoc)**

Append to `tests/test_render_paper.py`:

```python
TABLE_MD = (
    "| Komponente | Pfad |\n|---|---|\n| Wiki | /wiki |\n| Schema | /schema |\n| Skripte | /scripts |\n"
    "\nText.\n\n"
    "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |\n| 5 | 6 | 7 | 8 |\n| 9 | 10 | 11 | 12 |\n"
)

needs_pandoc = pytest.mark.skipif(
    rp.check_dependencies(which=lambda n: __import__("shutil").which(n) if n == "pandoc" else "x") != [],
    reason="pandoc not installed",
)


@needs_pandoc
def test_lua_filter_converts_tables_to_floats(tmp_path):
    filt = Path(rp.__file__).parent / "filters" / "twocolumn_tables.lua"
    src = tmp_path / "t.md"
    src.write_text(TABLE_MD, encoding="utf-8")
    out = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(filt)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "longtable" not in out
    assert "\\begin{tabular}" in out
    assert "\\begin{table}[t]" in out      # 2-column table → column float
    assert "\\begin{table*}[t]" in out     # 4-column table → spanning float
    assert "\\endhead" not in out and "\\endlastfoot" not in out
    # \bottomrule must come after the body rows, before \end{tabular}
    assert out.index("Skripte") < out.index("\\bottomrule")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render_paper.py -q -k lua_filter`
Expected: FAIL — pandoc errors because the filter file does not exist.

- [ ] **Step 3: Write the Lua filter**

Create `render/filters/twocolumn_tables.lua`:

```lua
-- Convert every table from pandoc's longtable output (which errors inside
-- LaTeX \twocolumn) into a tabular wrapped in a float: `table` for narrow
-- tables, `table*` (spans both columns) for wide ones (>= 4 columns).
local WIDE_COLUMNS = 4

function Table(tbl)
  local ncols = #tbl.colspecs
  local caption = pandoc.utils.stringify(tbl.caption.long)
  tbl.caption = pandoc.Caption()

  local latex = pandoc.write(pandoc.Pandoc({ tbl }), "latex")
  latex = latex:gsub("\\begin{longtable}%[[^%]]*%]", "\\begin{tabular}")
  latex = latex:gsub("\\end{longtable}", "\\end{tabular}")

  -- longtable emits: header lines, \endhead, footer lines (\bottomrule),
  -- \endlastfoot, body rows. Drop the markers and move the footer to the end.
  local out, footer, in_footer = {}, {}, false
  for line in (latex .. "\n"):gmatch("(.-)\n") do
    if line == "\\endfirsthead" or line == "\\endfoot" then
      -- drop
    elseif line == "\\endhead" then
      in_footer = true
    elseif line == "\\endlastfoot" then
      in_footer = false
    elseif in_footer then
      table.insert(footer, line)
    elseif line == "\\end{tabular}" then
      for _, f in ipairs(footer) do table.insert(out, f) end
      table.insert(out, line)
    else
      table.insert(out, line)
    end
  end

  local env = (ncols >= WIDE_COLUMNS) and "table*" or "table"
  local pieces = { "\\begin{" .. env .. "}[t]", "\\centering", "\\small",
                   table.concat(out, "\n") }
  if caption ~= "" then
    table.insert(pieces, "\\caption{" .. caption .. "}")
  end
  table.insert(pieces, "\\end{" .. env .. "}")
  return pandoc.RawBlock("latex", table.concat(pieces, "\n"))
end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_render_paper.py -q -k lua_filter`
Expected: PASS.

- [ ] **Step 5: Template — add `classoption` + `columnsep`**

In `render/templates/paper.latex` change line 1:

```latex
\documentclass[a4paper,11pt$if(classoption)$,$classoption$$endif$]{article}
```

and directly after the `\usepackage{calc}` line add:

```latex
\setlength{\columnsep}{0.8cm}
```

(no-op in single column; spacing for two-column).

- [ ] **Step 6: Run the existing template compile test (regression)**

Run: `python -m pytest tests/test_render_paper.py -q -k template_compiles`
Expected: PASS (single-column output unchanged — no `classoption` set means the conditional emits nothing).

- [ ] **Step 7: Commit**

```bash
git add render/filters/twocolumn_tables.lua render/templates/paper.latex tests/test_render_paper.py
git commit -m "feat(v2): Lua filter longtable->floats + classoption template hook"
```

---

### Task 6: `render_paper.py` — flags, `run_paperchart`, pipeline wiring

**Files:**
- Modify: `render/render_paper.py`
- Modify: `tests/test_render_paper.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_render_paper.py`:

```python
def test_build_pandoc_cmd_two_column_adds_filter_and_classoption():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="two")
    i = cmd.index("--lua-filter")
    assert cmd[i + 1].endswith("twocolumn_tables.lua")
    j = cmd.index("-V")
    assert cmd[j + 1] == "classoption=twocolumn"
    assert cmd[-2:] == ["-o", "out.pdf"]


def test_build_pandoc_cmd_one_column_has_no_filter():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="one")
    assert "--lua-filter" not in cmd and "-V" not in cmd


def test_run_paperchart_returns_none_on_bad_spec(tmp_path, capsys):
    result = rp.run_paperchart("kaputt: [", tmp_path / "c.pdf")
    assert result is None
    assert "paperchart skipped" in capsys.readouterr().err


def _render_with_stubs(tmp_path, md_text, **kwargs):
    """Run rp.render with pandoc/mmdc/charts stubbed out; return processed.md."""
    src = tmp_path / "report.md"
    src.write_text(md_text, encoding="utf-8")
    out_pdf = tmp_path / "out.pdf"
    calls = {}

    def fake_run(cmd, check):
        calls["pandoc"] = cmd

    rp.render(
        src, out_pdf, tmp_path, run=fake_run,
        mmdc_runner=lambda code, p: Path(p).write_bytes(b"%PDF-"),
        **kwargs,
    )
    processed = (tmp_path / ".render" / "processed.md").read_text(encoding="utf-8")
    return processed, calls


GOOD_BLOCK = "```paperchart\ntype: bar\nlabels: [a, b, c]\nseries: [{values: [1, 2, 3]}]\n```\n"
CHARTABLE_TABLE = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n"


def test_render_charts_off_strips_blocks(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + GOOD_BLOCK, charts="off")
    assert "paperchart" not in processed and "![](" not in processed


@pytest.mark.skipif(
    __import__("charts").charts_available() is not None, reason="chart deps missing"
)
def test_render_charts_blocks_renders_figures(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + GOOD_BLOCK, charts="blocks")
    assert "![](" in processed and "chart-" in processed


@pytest.mark.skipif(
    __import__("charts").charts_available() is not None, reason="chart deps missing"
)
def test_render_charts_auto_falls_back_to_autodetect(tmp_path):
    processed, _ = _render_with_stubs(tmp_path, "# T\n\n" + CHARTABLE_TABLE, charts="auto")
    assert "autochart-" in processed


@pytest.mark.skipif(
    __import__("charts").charts_available() is not None, reason="chart deps missing"
)
def test_render_charts_auto_no_fallback_when_blocks_exist(tmp_path):
    md = "# T\n\n" + GOOD_BLOCK + "\n" + CHARTABLE_TABLE
    processed, _ = _render_with_stubs(tmp_path, md, charts="auto")
    assert "chart-" in processed and "autochart-" not in processed


def test_render_two_column_uses_filter(tmp_path):
    _, calls = _render_with_stubs(tmp_path, "# T\n\nText.\n", layout="two")
    assert any(str(a).endswith("twocolumn_tables.lua") for a in calls["pandoc"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_render_paper.py -q`
Expected: new tests FAIL (`build_pandoc_cmd` rejects `layout` kwarg; `run_paperchart` missing).

- [ ] **Step 3: Implement**

In `render/render_paper.py`:

Replace `build_pandoc_cmd` with:

```python
def build_pandoc_cmd(input_path, output_path, template_path, resource_path,
                     *, layout: str = "one") -> list[str]:
    """Construct the Pandoc argv for a German PDF via Tectonic."""
    cmd = [
        "pandoc",
        str(input_path),
        "--template", str(template_path),
        "--pdf-engine=tectonic",
        "--number-sections",
        f"--resource-path={resource_path}",
    ]
    if layout == "two":
        lua = Path(__file__).parent / "filters" / "twocolumn_tables.lua"
        cmd += ["--lua-filter", str(lua), "-V", "classoption=twocolumn"]
    cmd += ["-o", str(output_path)]
    return cmd
```

Add after `run_mmdc`:

```python
def run_paperchart(code: str, out_path) -> Path | None:
    """Parse + render one paperchart block; None (and a warning) on failure."""
    import charts

    try:
        spec = charts.parse_paperchart(code)
        charts.render_chart(spec, out_path)
        return Path(out_path)
    except charts.ChartSpecError as e:
        print(f"paperchart skipped: {e}", file=sys.stderr)
        return None
    except Exception as e:  # matplotlib failures etc. — never fatal
        print(f"paperchart render failed: {e}", file=sys.stderr)
        return None


def run_autochart(spec, out_path) -> Path | None:
    """Render one auto-detected chart spec; None (and a warning) on failure."""
    import charts

    try:
        charts.render_chart(spec, out_path)
        return Path(out_path)
    except Exception as e:
        print(f"autochart render failed: {e}", file=sys.stderr)
        return None
```

In `render()`: change the signature line to

```python
def render(input_md, output_pdf, project_root, *, title=None, authors=None,
           dateline=None, work_dir=None, run=subprocess.run, mmdc_runner=None,
           layout: str = "one", charts: str = "blocks") -> Path:
```

and insert between the `resolve_images` and `render_mermaid_blocks` lines:

```python
    import charts as charts_mod

    figures = work_dir / "figures"
    if charts != "off" and (warn := charts_mod.charts_available()):
        print(warn, file=sys.stderr)
        charts = "off"
    if charts == "off":
        md, _ = pre.render_paperchart_blocks(md, figures, lambda code, p: None)
    else:
        md, n_blocks = pre.render_paperchart_blocks(md, figures, run_paperchart)
        if charts == "auto" and n_blocks == 0:
            md = pre.inject_autodetected_charts(
                md, figures, run_autochart, charts_mod.autodetect_charts
            )
```

and change the `build_pandoc_cmd` call to:

```python
    cmd = build_pandoc_cmd(processed_path, output_pdf, template, project_root,
                           layout=layout)
```

In `main()` add after the `--dateline` argument:

```python
    parser.add_argument("--layout", choices=["one", "two"], default="one",
                        help="page layout: one or two columns")
    parser.add_argument("--charts", choices=["auto", "blocks", "off"], default="blocks",
                        help="paperchart handling: blocks only, +autodetect fallback, or off")
```

and pass them in the `render(...)` call:

```python
    out = render(
        args.input, args.output, args.project,
        title=args.title, authors=args.authors, dateline=args.dateline,
        layout=args.layout, charts=args.charts,
    )
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests -q`
Expected: all PASS (existing 30 + all new).

- [ ] **Step 5: Commit**

```bash
git add render/render_paper.py tests/test_render_paper.py
git commit -m "feat(v2): --layout/--charts flags and chart pipeline wiring"
```

---

### Task 7: End-to-end acceptance — two-column + auto-charts PDF

**Files:**
- Modify: `tests/test_render_paper.py` (append)

- [ ] **Step 1: Write the integration test (real toolchain)**

Append to `tests/test_render_paper.py`:

```python
@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
@pytest.mark.skipif(
    __import__("charts").charts_available() is not None, reason="chart deps missing"
)
def test_two_column_pdf_with_autochart_end_to_end(tmp_path):
    md = tmp_path / "report.md"
    md.write_text(
        "# Zweispaltiger Testbericht\n\n"
        "## Zusammenfassung\nKurzfassung des Berichts.\n\n"
        "## Messwerte\n\n"
        "| Indexgröße | p50 | p99 |\n|---|---|---|\n"
        "| 10k | 12 | 40 |\n| 100k | 18 | 95 |\n| 1M | 35 | 210 |\n\n"
        "## Architektur\n\n"
        "| A | B | C | D |\n|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 |\n| 5 | 6 | 7 | 8 |\n| 9 | 1 | 2 | 3 |\n\n"
        "Fließtext danach mit Umlauten: äöüß.\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.pdf"
    rp.render(md, out, tmp_path, authors="Test Autor 123456",
              dateline="RWTH Aachen, Juni 2026", layout="two", charts="auto")
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 10_000
    assert (tmp_path / ".render" / "figures").glob("autochart-*.pdf")
```

- [ ] **Step 2: Run it (needs proxy for Tectonic fetches)**

Run (PowerShell, from the make-paper repo):
`$env:HTTPS_PROXY='http://127.0.0.1:10808'; $env:HTTP_PROXY='http://127.0.0.1:10808'; python -m pytest tests/test_render_paper.py -q -k end_to_end`
Expected: PASS. If Tectonic fails on a missing package, check the proxy env vars are set in the SAME invocation.

- [ ] **Step 3: Acceptance run on the real CLEAR paper**

Run (PowerShell):

```powershell
$env:HTTPS_PROXY='http://127.0.0.1:10808'; $env:HTTP_PROXY='http://127.0.0.1:10808'; python render/render_paper.py --input "F:\____IL_AI\CLEAR\Papers\CLEAR Paper.md" --output "F:\____IL_AI\CLEAR\Papers\CLEAR Paper (zweispaltig).pdf" --project "F:\____IL_AI\CLEAR" --authors "Petr Nasybulin 478314, Philipp Gembruch 472685" --dateline "RWTH Aachen, Juni 2026" --layout two --charts auto
```

Expected: `Wrote ...CLEAR Paper (zweispaltig).pdf`. Open it; verify: two columns, tables as floats (wide ones spanning both columns), at least one chart figure if the report has a chartable table (if it has none, confirm the run notes nothing chartable and still produces a clean two-column PDF).

- [ ] **Step 4: Run the full suite once more**

Run: `python -m pytest tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_render_paper.py
git commit -m "test(v2): end-to-end two-column + autochart acceptance"
```

---

### Task 8: Subagent protocol — preconditions, prompt, flags, retry, review loop

**Files:**
- Modify: `agents/make-paper.md`
- Copy to: `C:\Users\il720506\.claude\agents\make-paper.md`

- [ ] **Step 1: Update the frontmatter `description`**

Replace the precondition sentence in the `description:` block with:

```
PRECONDITION the MAIN agent MUST satisfy before delegating
(this subagent cannot ask the user anything): ask the user (1) which notebooklm
profile / Google account, (2) the desired notebook name, (3) layout: one- or
two-column, and (4) whether to include data charts; then delegate passing the
project path, profile, notebook name, layout, and charts choice in the task
prompt. When this agent returns, open the produced PDF for the user (or the
Markdown report if it reports that PDF rendering was skipped), then ask the
user what to change in the graphics (remove/add/retype charts); apply chart
changes by editing the ```paperchart blocks in Papers/<name>.md and re-running
render/render_paper.py with the same flags — a local loop, no NotebookLM calls.
```

- [ ] **Step 2: Extend the Step 6 NotebookLM prompt**

After the existing PROMPT blockquote (ends with `Institutszeile genau: „<dateline>".`), append to the blockquote (only when charts were requested):

```
> Wo der Bericht numerische Daten aus den Quellen zitiert, füge zusätzlich
> einen Codeblock mit der Sprache „paperchart" ein (YAML: type: bar|line|pie;
> title; labels: [...]; series: [- name, values: [...]]; bei pie genau eine
> Serie; values müssen exakt den Zahlen aus den Quellen entsprechen — erfinde
> keine Werte). Beispiel:
> ```paperchart
> type: bar
> title: "Antwortzeiten"
> labels: ["10k", "100k"]
> series:
>   - name: "p50"
>     values: [12, 18]
> ```
```

- [ ] **Step 3: Update Step 8 (render) with flags + retry rule**

Replace the renderer command with:

```
   python "%USERPROFILE%\.claude\make-paper\render\render_paper.py" \
     --input  "<project_path>\Papers\<notebook_name>.md" \
     --output "<project_path>\Papers\<notebook_name>.pdf" \
     --project "<project_path>" \
     --authors "<AUTHOR_LINE>" --dateline "<dateline>" \
     --layout <one|two, as delegated> --charts <auto if charts requested, else off>
```

and add to the result-handling list:

```
   - Two-column failure: if --layout two was requested and the renderer fails,
     retry ONCE with --layout one (note the downgrade in your summary) before
     degrading to the Markdown-only outcome.
```

- [ ] **Step 4: Update Step 10 (summary contract)**

Append to Step 10:

```
    Also report: how many charts the report contains (LLM-authored vs
    auto-detected) and the layout actually used (two / downgraded-to-one /
    one), so the main agent can run the graphics review loop with the user.
```

- [ ] **Step 5: Reinstall and verify**

Run (PowerShell):
`Copy-Item "C:\Users\il720506\.claude\make-paper\agents\make-paper.md" "C:\Users\il720506\.claude\agents\make-paper.md" -Force`
Then: `Select-String -Path "C:\Users\il720506\.claude\agents\make-paper.md" -Pattern "paperchart" | Measure-Object | Select-Object Count`
Expected: Count ≥ 2.

- [ ] **Step 6: Commit**

```bash
git add agents/make-paper.md
git commit -m "feat(v2): subagent protocol - chart/layout preconditions, prompt, retry, review loop"
```

---

### Task 9: Docs + wrap-up

**Files:**
- Modify: `README.md` (make-paper repo)

- [ ] **Step 1: Document v2 in the README**

Add to `README.md` under the Subsystem B section:

```markdown
### v2: charts + two-column

- `--layout one|two` (default `one`): two-column uses `classoption=twocolumn`
  plus `render/filters/twocolumn_tables.lua` (tables become `table`/`table*`
  floats; pandoc's `longtable` cannot live inside `twocolumn`).
- `--charts auto|blocks|off` (default `blocks`): renders ```paperchart YAML
  blocks (bar/line/pie) via matplotlib to vector PDF figures; `auto` adds
  table auto-detection as fallback when the report has no blocks; `off`
  strips blocks. Soft deps: `pip install pyyaml matplotlib` — missing deps
  skip charts with a warning, never fail the render.
- Chart edits after a run are local: edit the ```paperchart blocks in
  `Papers/<name>.md`, re-run the renderer.
```

- [ ] **Step 2: Full suite + gate check**

Run: `python -m pytest tests -q` → all PASS.
Then from `F:\____IL_AI\CLEAR`: `python scripts/audit_public.py` → clean (re-clean `.claude/settings.local.json` if machine-local forward-slash paths crept in).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(v2): charts + two-column usage"
```

- [ ] **Step 4: Update session memory** (main session does this, not a subagent): mark v2 BUILT in `make-paper-project.md` with test count and acceptance-run result; note the new flags in `make-paper-toolchain.md` only if toolchain facts changed.

---

## Self-review (done at planning time)

- **Spec coverage:** paperchart spec/validation → T1; matplotlib rendering → T2; autodetect heuristics → T3; preprocess transforms + fallback trigger (count includes invalid blocks) → T4; Lua filter + classoption + byte-identical single column → T5 (regression step 6); CLI flags, lazy deps, skip-on-missing, pipeline order → T6; end-to-end acceptance incl. real CLEAR paper → T7; four pre-run questions, German prompt extension, retry-to-one-column, review loop → T8; docs → T9. Error-handling table of the spec: malformed block (T1 parse + T6 `run_paperchart`), missing deps (T2 `charts_available` + T6 wiring), two-column failure retry (T8), nothing-chartable (T7 step 3).
- **Type consistency:** `runner(code, out_path) -> path|None` for blocks vs `runner(spec, out_path) -> path|None` for autocharts — distinct names `run_paperchart`/`run_autochart` wired accordingly. `autodetect_charts -> list[(ChartSpec, int)]` consumed by `inject_autodetected_charts` via `detect`.
- **Placeholders:** none; all steps carry code/commands/expected output.
