"""paperchart spec parsing, matplotlib rendering, and table auto-detection
for make-paper Subsystem B v2. PyYAML and matplotlib are imported lazily so
the rest of the renderer works without them."""
from __future__ import annotations

import re
from dataclasses import dataclass
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
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_SEP = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_NUMCELL = re.compile(r"^\s*[-+]?\d[\d.,]*\s*(?:%|[A-Za-zµ°/²³·]{1,6})?\s*$")
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
    # Bare numbers (no unit suffix) in the first column mean it is data, not
    # labels — "12" is data, but "10k" or "2,0 mm" still label categories.
    labels_numeric = all(
        re.fullmatch(r"\s*[-+]?[\d.,]+\s*", x) and _to_number(x) is not None
        for x in labels
    )
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
