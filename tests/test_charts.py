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
