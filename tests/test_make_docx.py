import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "render"))

import make_docx as md


def _make_pdf(path: Path, text: str) -> None:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    doc.save(str(path))
    doc.close()


needs_pdf2docx = pytest.mark.skipif(md.docx_available() is not None,
                                    reason="pdf2docx not installed")


@needs_pdf2docx
def test_convert_produces_valid_docx_with_text(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf(pdf, "Kugelfallviskosimetrie")
    out = md.convert(pdf)
    assert out == tmp_path / "paper.docx"
    assert out.is_file()
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Kugelfallviskosimetrie" in xml


@needs_pdf2docx
def test_convert_honors_explicit_output_path(tmp_path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf(pdf, "Inhalt")
    out = md.convert(pdf, tmp_path / "sub" / "anders.docx")
    assert out == tmp_path / "sub" / "anders.docx"
    assert out.is_file()


def test_main_errors_when_dep_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(md, "docx_available", lambda: "docx skipped (pdf2docx not installed)")
    rc = md.main(["--input", str(tmp_path / "x.pdf")])
    assert rc == 2
    assert "pdf2docx" in capsys.readouterr().err


def test_main_errors_when_input_missing(tmp_path, capsys):
    rc = md.main(["--input", str(tmp_path / "fehlt.pdf")])
    assert rc == 1
    assert "fehlt.pdf" in capsys.readouterr().err


def test_main_converts_and_reports(tmp_path, monkeypatch, capsys):
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-fake")
    seen = {}

    def fake_convert(inp, outp=None):
        seen["args"] = (Path(inp), outp)
        return tmp_path / "p.docx"

    monkeypatch.setattr(md, "convert", fake_convert)
    rc = md.main(["--input", str(pdf)])
    assert rc == 0
    assert seen["args"] == (pdf, None)
    assert "p.docx" in capsys.readouterr().out
