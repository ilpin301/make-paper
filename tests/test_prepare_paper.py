import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prepare_paper as pp


def test_german_month_returns_native_name():
    assert pp.german_month(1) == "Januar"
    assert pp.german_month(3) == "März"
    assert pp.german_month(6) == "Juni"
    assert pp.german_month(12) == "Dezember"


def test_german_dateline_uses_current_month_and_year():
    line = pp.german_dateline("RWTH Aachen", date(2026, 6, 10))
    assert line == "RWTH Aachen, Juni 2026"


def test_parse_authors_reads_names_and_institution_field():
    md = "# Authors\n- Max Mustermann\n- Erika Musterfrau\n\ninstitution: RWTH Aachen\n"
    names, institution = pp.parse_authors(md)
    assert names == ["Max Mustermann", "Erika Musterfrau"]
    assert institution == "RWTH Aachen"


def test_parse_authors_falls_back_to_dateline_line():
    md = "- Max Mustermann\n\nRWTH Aachen, Juni 2026\n"
    names, institution = pp.parse_authors(md)
    assert names == ["Max Mustermann"]
    assert institution == "RWTH Aachen"
