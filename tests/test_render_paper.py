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
