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


def _make_sample(dirpath: Path, name: str):
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / name).write_text("x", encoding="utf-8")


def test_resolve_assets_prefers_project_over_global(tmp_path):
    project = tmp_path / "proj"
    glob = tmp_path / "global"
    _make_sample(project / "Samples", "a.md")
    (project / "Authors").mkdir(parents=True)
    (project / "Authors" / "authors.md").write_text("- A\ninstitution: X", encoding="utf-8")
    _make_sample(glob / "Samples", "g.md")
    (glob / "authors.md").write_text("- G\ninstitution: Y", encoding="utf-8")

    assets = pp.resolve_assets(project, glob)
    assert assets.samples_dir == project / "Samples"
    assert assets.authors_file == project / "Authors" / "authors.md"


def test_resolve_assets_falls_back_to_global(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    glob = tmp_path / "global"
    _make_sample(glob / "Samples", "g.md")
    (glob / "authors.md").write_text("- G\ninstitution: Y", encoding="utf-8")

    assets = pp.resolve_assets(project, glob)
    assert assets.samples_dir == glob / "Samples"
    assert assets.authors_file == glob / "authors.md"


def test_resolve_assets_raises_when_nothing_found(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    glob = tmp_path / "global"
    glob.mkdir()
    import pytest
    with pytest.raises(FileNotFoundError):
        pp.resolve_assets(project, glob)


def test_collect_wiki_sources_returns_md_excluding_index(tmp_path):
    wiki = tmp_path / "Wiki" / "Topics"
    wiki.mkdir(parents=True)
    (wiki / "a.md").write_text("a", encoding="utf-8")
    (wiki / "index.md").write_text("nav", encoding="utf-8")
    (tmp_path / "Wiki" / "Concepts").mkdir()
    (tmp_path / "Wiki" / "Concepts" / "b.md").write_text("b", encoding="utf-8")
    # noise outside Wiki/ must be ignored
    (tmp_path / "Raw").mkdir()
    (tmp_path / "Raw" / "c.md").write_text("c", encoding="utf-8")

    sources = pp.collect_wiki_sources(tmp_path)
    names = sorted(p.name for p in sources)
    assert names == ["a.md", "b.md"]


def test_stage_samples_renames_zero_padded_keeps_extension(tmp_path):
    src = tmp_path / "Samples"
    src.mkdir()
    (src / "zeta.md").write_text("z", encoding="utf-8")
    (src / "alpha.docx").write_text("a", encoding="utf-8")
    dest = tmp_path / "staging"

    staged = pp.stage_samples([src / "alpha.docx", src / "zeta.md"], dest)
    names = [p.name for p in staged]
    assert names == ["sample-01.docx", "sample-02.md"]
    assert (dest / "sample-01.docx").read_text(encoding="utf-8") == "a"
    assert (dest / "sample-02.md").read_text(encoding="utf-8") == "z"


def test_build_manifest_end_to_end(tmp_path):
    project = tmp_path / "proj"
    (project / "Wiki" / "Topics").mkdir(parents=True)
    (project / "Wiki" / "Topics" / "topic.md").write_text("t", encoding="utf-8")
    (project / "Samples").mkdir()
    (project / "Samples" / "ref.md").write_text("style", encoding="utf-8")
    (project / "Authors").mkdir()
    (project / "Authors" / "authors.md").write_text(
        "- Max Mustermann\ninstitution: RWTH Aachen\n", encoding="utf-8"
    )
    glob = tmp_path / "global"
    glob.mkdir()
    staging = tmp_path / "staging"

    manifest = pp.build_manifest(
        project_path=project, global_root=glob, staging_dir=staging,
        today=date(2026, 6, 10),
    )

    assert [Path(p).name for p in manifest["wiki_sources"]] == ["topic.md"]
    assert [Path(p).name for p in manifest["sample_sources"]] == ["sample-01.md"]
    assert Path(manifest["authors_source"]).name == "authors.md"
    assert manifest["author_names"] == ["Max Mustermann"]
    assert manifest["dateline"] == "RWTH Aachen, Juni 2026"
    # round-trips as JSON
    import json
    json.dumps(manifest)


def test_parse_authors_reads_name_with_matriculation_lines():
    md = "Petr Nasybulin 478314\nPhilipp Gembruch 472685\n\nRWTH Aachen, Juni 2026\n"
    names, institution = pp.parse_authors(md)
    assert names == ["Petr Nasybulin 478314", "Philipp Gembruch 472685"]
    assert institution == "RWTH Aachen"


def test_resolve_assets_finds_autors_spelling(tmp_path):
    project = tmp_path / "proj"
    glob = tmp_path / "global"
    _make_sample(project / "Samples", "a.md")
    (project / "Autors").mkdir(parents=True)
    (project / "Autors" / "autors.md").write_text(
        "Petr Nasybulin 478314\n\nRWTH Aachen, Juni 2026", encoding="utf-8"
    )
    _make_sample(glob / "Samples", "g.md")
    (glob / "authors.md").write_text("- G\ninstitution: Y", encoding="utf-8")

    assets = pp.resolve_assets(project, glob)
    assert assets.authors_file == project / "Autors" / "autors.md"
