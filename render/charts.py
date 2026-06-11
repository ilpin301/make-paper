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
    if spec.title:
        ax.set_title(spec.title)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
