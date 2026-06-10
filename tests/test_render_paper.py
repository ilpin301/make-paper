import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))

import render_paper as rp


def test_check_dependencies_reports_missing():
    present = {"pandoc"}
    fake_which = lambda name: "/usr/bin/" + name if name in present else None
    missing = rp.check_dependencies(which=fake_which)
    assert missing == ["mmdc", "tectonic"]


def test_check_dependencies_none_missing():
    fake_which = lambda name: "/usr/bin/" + name
    assert rp.check_dependencies(which=fake_which) == []


def test_build_pandoc_cmd_has_template_and_tectonic():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj")
    assert cmd[0] == "pandoc"
    assert "in.md" in cmd
    assert "--template" in cmd and "tpl.latex" in cmd
    assert "--pdf-engine=tectonic" in cmd
    assert "--number-sections" in cmd
    assert "--resource-path=/proj" in cmd
    assert cmd[-2:] == ["-o", "out.pdf"]


def test_run_mmdc_invokes_mmdc_with_io(tmp_path):
    seen = {}

    def fake_run(argv, check):
        seen["argv"] = argv
        seen["check"] = check

    out = tmp_path / "d.pdf"
    rp.run_mmdc("graph TD; A-->B", out, run=fake_run)
    assert seen["argv"][0] == "mmdc"
    assert "-i" in seen["argv"] and "-o" in seen["argv"]
    assert str(out) in seen["argv"]
    assert seen["check"] is True
