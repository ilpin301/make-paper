# make-paper v2.1 Styling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 8 approved styling rules (spec: `docs/2026-06-11-make-paper-v2.1-styling-design.md`): English/label-free italic full-width abstract, deduplicated author lines, trailing italic `[n]` references, numbered equations, fully centered table cells, sample-style figure captions, and 1/1.1/1.1.1 section numbering.

**Architecture:** Three new pure transforms in `render/preprocess.py` (author-line strip, heading promotion, references mover); `render/filters/paper_style.lua` replaces `twocolumn_tables.lua` and runs in BOTH layouts (numbered equations + centered float tables); template gets a `\paperhead` block (full-width italic abstract via `\twocolumn[{...}]`) and `caption` package; chart figures carry their titles as captions.

**Tech Stack:** Python 3.14, pytest, pandoc Lua filter, LaTeX (article/polyglossia/caption), matplotlib.

**Working directory:** `C:\Users\il720506\.claude\make-paper`. Pipeline order note: the spec lists strip→move→promote; implementation runs strip→**promote**→**move** so the references section can be emitted as an unnumbered level-1 heading (`# Literaturverzeichnis {-}`) without confusing the promotion's min-level scan. Outcome is identical, order is an internal detail.

---

### Task 1: `strip_author_lines`

**Files:** Modify `render/preprocess.py`, `tests/test_preprocess.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_preprocess.py`:

```python
AUTHORS = "Petr Nasybulin 478314, Philipp Gembruch 472685"
DATELINE = "RWTH Aachen, Juni 2026"


def test_strip_author_lines_removes_bold_duplicates():
    md = f"**{AUTHORS}**\n**{DATELINE}**\n\n## Einleitung\nText über {DATELINE}.\n"
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    assert AUTHORS not in out.split("## Einleitung")[0]
    assert "## Einleitung" in out
    # mentions inside body prose are untouched
    assert f"Text über {DATELINE}." in out


def test_strip_author_lines_only_before_first_heading():
    md = f"## Anhang\n{AUTHORS}\n"
    out = pre.strip_author_lines(md, AUTHORS, DATELINE)
    assert AUTHORS in out  # after a heading → body content, kept


def test_strip_author_lines_noop_without_matches():
    md = "Ganz normaler Text.\n\n## Einleitung\n"
    assert pre.strip_author_lines(md, AUTHORS, DATELINE) == md


def test_strip_author_lines_noop_with_empty_args():
    md = f"**{AUTHORS}**\n\n## E\n"
    assert pre.strip_author_lines(md, "", "") == md
```

- [ ] **Step 2: Run** `python -m pytest tests/test_preprocess.py -q -k strip_author` → FAIL (AttributeError).

- [ ] **Step 3: Implement** — append to `render/preprocess.py`:

```python
def strip_author_lines(md: str, authors: str, dateline: str) -> str:
    """Drop pre-heading lines duplicating the authors line or the dateline.

    Only exact content matches (emphasis markers and whitespace ignored) in
    the region BEFORE the first ATX heading are removed — the title block
    already carries authors + dateline (spec rule 3).
    """
    targets = {" ".join(t.split()) for t in (authors, dateline) if t and t.strip()}
    if not targets:
        return md
    out = []
    seen_heading = False
    for line in md.splitlines():
        if _HEADING.match(line):
            seen_heading = True
        if not seen_heading:
            content = " ".join(line.replace("*", "").replace("_", "").split())
            if content in targets:
                continue
        out.append(line)
    return "\n".join(out)
```

- [ ] **Step 4: Run** `python -m pytest tests/test_preprocess.py -q` → all PASS.
- [ ] **Step 5: Commit** `git add render/preprocess.py tests/test_preprocess.py && git commit -m "feat(v2.1): strip duplicated author/dateline lines before first heading"`

---

### Task 2: `promote_headings`

**Files:** Modify `render/preprocess.py`, `tests/test_preprocess.py`

- [ ] **Step 1: Failing tests:**

```python
def test_promote_headings_shifts_h3_to_h1():
    md = "### Einleitung\nText\n#### Detail\n### Fazit\n"
    out = pre.promote_headings(md)
    assert "# Einleitung" in out and "## Detail" in out and "# Fazit" in out
    assert "###" not in out


def test_promote_headings_noop_when_h1_present():
    md = "# Einleitung\n### Detail\n"
    assert pre.promote_headings(md) == md


def test_promote_headings_ignores_code_fences():
    md = "```paperchart\n### not a heading\n```\n## Echt\n"
    out = pre.promote_headings(md)
    assert "### not a heading" in out and "# Echt" in out
```

- [ ] **Step 2: Run** `-k promote` → FAIL.
- [ ] **Step 3: Implement:**

```python
def promote_headings(md: str) -> str:
    """Uniformly shift ATX headings so the smallest level present becomes 1.

    Gives --number-sections the 1 / 1.1 / 1.1.1 scheme (spec rule 8).
    Fenced code blocks are left untouched.
    """
    lines = md.splitlines()
    in_fence = False
    levels = []
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and (m := _HEADING.match(line)):
            levels.append(len(m.group(1)))
    shift = min(levels) - 1 if levels else 0
    if shift <= 0:
        return md
    out = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and (m := _HEADING.match(line)):
            line = "#" * (len(m.group(1)) - shift) + " " + m.group(2)
        out.append(line)
    return "\n".join(out)
```

- [ ] **Step 4: Run** full preprocess file → all PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(v2.1): promote heading levels for 1/1.1/1.1.1 numbering"`

---

### Task 3: `move_references_last`

**Files:** Modify `render/preprocess.py`, `tests/test_preprocess.py`

- [ ] **Step 1: Failing tests:**

```python
REFS_MD = (
    "# Einleitung\nText.\n\n"
    "# Literaturverzeichnis\n"
    "1. RWTH Aachen: Anleitung. Aachen.\n"
    "2. Messprotokoll intern.\n\n"
    "# Fazit\nSchluss.\n"
)


def test_move_references_last_moves_and_renumbers():
    out = pre.move_references_last(REFS_MD)
    assert out.rstrip().endswith("*[2] Messprotokoll intern.*")
    assert "*[1] RWTH Aachen: Anleitung. Aachen.*" in out
    assert "1. RWTH" not in out
    # section heading is unnumbered and last
    assert out.index("# Fazit") < out.index("# Literaturverzeichnis {-}")


def test_move_references_handles_bullets_and_alt_titles():
    md = "# A\n\n## Quellen\n- Erste Quelle\n- Zweite Quelle\n\n# B\nText.\n"
    out = pre.move_references_last(md)
    assert out.index("# B") < out.index("# Literaturverzeichnis {-}")
    assert "*[1] Erste Quelle*" in out and "*[2] Zweite Quelle*" in out


def test_move_references_noop_when_absent():
    md = "# A\nText ohne Quellenangaben.\n"
    assert pre.move_references_last(md) == md
```

- [ ] **Step 2: Run** `-k references` → FAIL.
- [ ] **Step 3: Implement:**

```python
_REF_TITLES = {"literaturverzeichnis", "literatur", "quellen", "referenzen"}
_REF_ENTRY = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+(.*\S)\s*$")


def move_references_last(md: str) -> str:
    """Move the references section to the end; entries become '*[n] …*'.

    The section is retitled to an unnumbered '# Literaturverzeichnis {-}'
    (spec rule 4). Recognized titles: Literaturverzeichnis, Literatur,
    Quellen, Referenzen. Absent section → no-op.
    """
    lines = md.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().lower() in _REF_TITLES:
            start, level = i, len(m.group(1))
            break
    if start is None:
        return md
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    entries = []
    for line in lines[start + 1:end]:
        if not line.strip():
            continue
        m = _REF_ENTRY.match(line)
        entries.append(m.group(1) if m else line.strip())
    body = lines[:start] + lines[end:]
    while body and not body[-1].strip():
        body.pop()
    out = body + ["", "# Literaturverzeichnis {-}", ""]
    out += [f"*[{n}] {text}*" for n, text in enumerate(entries, 1)]
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Run** full preprocess file → all PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(v2.1): references section moved last with italic [n] entries"`

---

### Task 4: `paper_style.lua` replaces `twocolumn_tables.lua`

**Files:** Create `render/filters/paper_style.lua`; Delete `render/filters/twocolumn_tables.lua`; Modify `render/render_paper.py` (`build_pandoc_cmd`), `tests/test_render_paper.py`

- [ ] **Step 1: Rewrite the filter integration test.** In `tests/test_render_paper.py` REPLACE `test_lua_filter_converts_tables_to_floats` with:

```python
@needs_pandoc
def test_paper_style_filter_tables_and_equations(tmp_path):
    filt = Path(rp.__file__).parent / "filters" / "paper_style.lua"
    src = tmp_path / "t.md"
    src.write_text(
        TABLE_MD + "\nFormel:\n\n$$E = m c^2$$\n\n![Testtitel](bild.pdf)\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        ["pandoc", str(src), "-t", "latex", "--lua-filter", str(filt)],
        capture_output=True, text=True, check=True,
    ).stdout
    # tables: floats, centered, no longtable leftovers
    assert "longtable" not in out
    assert "\\begin{table}[t]" in out and "\\begin{table*}[t]" in out
    assert "\\endhead" not in out
    assert "{@{}cc@{}}" in out          # simple cols centered
    # display math: numbered equation
    assert "\\begin{equation}" in out and "E = m c^2" in out
    assert "\\[" not in out
    # captioned image survives as a figure with caption
    assert "\\caption{Testtitel" in out
```

Also UPDATE the two pandoc-cmd tests:

```python
def test_build_pandoc_cmd_two_column_adds_filter_and_classoption():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="two")
    i = cmd.index("--lua-filter")
    assert cmd[i + 1].endswith("paper_style.lua")
    j = cmd.index("-V")
    assert cmd[j + 1] == "classoption=twocolumn"
    assert cmd[-2:] == ["-o", "out.pdf"]


def test_build_pandoc_cmd_one_column_has_filter_but_no_classoption():
    cmd = rp.build_pandoc_cmd("in.md", "out.pdf", "tpl.latex", "/proj", layout="one")
    i = cmd.index("--lua-filter")
    assert cmd[i + 1].endswith("paper_style.lua")
    assert "-V" not in cmd
```

And in `test_render_two_column_uses_filter` change the endswith target to `paper_style.lua`.

- [ ] **Step 2: Run** `-k "paper_style or pandoc_cmd"` → FAIL.
- [ ] **Step 3: Create `render/filters/paper_style.lua`** (start from `twocolumn_tables.lua`'s Table function):

```lua
-- make-paper paper_style filter (applied in BOTH layouts):
--  * tables  -> tabular in table/table* floats, cells centered H+V
--  * display math -> numbered equation environments
local WIDE_COLUMNS = 4

function Table(tbl)
  local ncols = #tbl.colspecs
  local caption = pandoc.utils.stringify(tbl.caption.long)
  tbl.caption = pandoc.Caption()
  for i, spec in ipairs(tbl.colspecs) do
    tbl.colspecs[i] = { pandoc.AlignCenter, spec[2] }
  end

  local latex = pandoc.write(pandoc.Pandoc({ tbl }), "latex")
  latex = latex:gsub("\\begin{longtable}%[[^%]]*%]", "\\begin{tabular}")
  latex = latex:gsub("\\end{longtable}", "\\end{tabular}")
  -- width-managed columns: p{} -> m{} (vertical centering)
  latex = latex:gsub("\\arraybackslash}p{", "\\arraybackslash}m{")

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

function Math(m)
  if m.mathtype == "DisplayMath" then
    return pandoc.RawInline("latex",
      "\\begin{equation}" .. m.text .. "\\end{equation}")
  end
end
```

- [ ] **Step 4: Update `build_pandoc_cmd`** in `render/render_paper.py`:

```python
    cmd = [
        "pandoc",
        str(input_path),
        "--template", str(template_path),
        "--pdf-engine=tectonic",
        "--number-sections",
        f"--resource-path={resource_path}",
        "--lua-filter", str(Path(__file__).parent / "filters" / "paper_style.lua"),
    ]
    if layout == "two":
        cmd += ["-V", "classoption=twocolumn"]
    cmd += ["-o", str(output_path)]
    return cmd
```

- [ ] **Step 5: Delete the old filter** `git rm render/filters/twocolumn_tables.lua`.
- [ ] **Step 6: Run** the full suite → all PASS.
- [ ] **Step 7: Commit** `git commit -m "feat(v2.1): paper_style.lua - numbered equations + centered float tables in all layouts"`

---

### Task 5: chart captions

**Files:** Modify `render/charts.py` (`render_chart`), `render/preprocess.py` (both chart transforms), `render/render_paper.py` (`run_paperchart`), tests.

Runner contract change: paperchart runner returns `(path, caption)` or `None`; autochart runner keeps returning `path|None` and preprocess reads `spec.title` for the caption.

- [ ] **Step 1: Failing tests.** In `tests/test_preprocess.py`, UPDATE the three paperchart tests' runner lambdas/asserts and the inject test:

```python
def test_render_paperchart_blocks_replaces_with_figure(tmp_path):
    def runner(code, out_path):
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path, "Mein Diagramm"

    out, count = pre.render_paperchart_blocks(PAPERCHART_MD, tmp_path, runner)
    assert count == 1
    assert "```paperchart" not in out
    assert "![Mein Diagramm](" in out and ".pdf)" in out
    assert "Vorher." in out and "Nachher." in out
```

(`drops_failed_block` and `counts_all_blocks` keep `lambda c, p: None` and still pass.)

```python
def test_inject_autodetected_charts_inserts_after_table(tmp_path):
    md = "| K | W |\n|---|---|\n| a | 1 |\n| b | 2 |\n| c | 3 |\n\nDanach.\n"

    class FakeSpec:
        title = "Autotitel"

    fake_spec = FakeSpec()

    def detect(text):
        return [(fake_spec, 4)]

    def runner(spec, out_path):
        assert spec is fake_spec
        Path(out_path).write_bytes(b"%PDF-fake")
        return out_path

    out = pre.inject_autodetected_charts(md, tmp_path, runner, detect)
    lines = out.splitlines()
    fig_idx = next(i for i, l in enumerate(lines) if l.startswith("![Autotitel]("))
    assert fig_idx > 4
    assert lines.index("Danach.") > fig_idx
```

In `tests/test_charts.py` add:

```python
@needs_deps
def test_render_chart_does_not_draw_title_inside(tmp_path):
    spec = charts.ChartSpec(type="bar", labels=["a"], series=[charts.Series("", [1.0])],
                            title="Nur als Caption")
    out = tmp_path / "t.pdf"
    charts.render_chart(spec, out)  # must not raise; title not drawn
    assert out.read_bytes()[:5] == b"%PDF-"
```

In `tests/test_render_paper.py`, `test_render_charts_blocks_renders_figures` additionally asserts the alt text: `assert "![" in processed and "](" in processed`.

- [ ] **Step 2: Run** → relevant tests FAIL (tuple contract not implemented).
- [ ] **Step 3: Implement.**

`render/preprocess.py` — in `render_paperchart_blocks.repl` replace the return with:

```python
        result = runner(code, out_dir / f"chart-{digest}.pdf")
        if not result:
            return ""
        path, caption = result
        return f"![{caption}]({Path(path).as_posix()})"
```

and in `inject_autodetected_charts` replace the insertion with:

```python
        result = runner(spec, out_dir / f"autochart-{n:02d}.pdf")
        if result:
            caption = getattr(spec, "title", "") or ""
            lines[end_idx + 1:end_idx + 1] = ["", f"![{caption}]({Path(result).as_posix()})"]
```

`render/render_paper.py` — `run_paperchart` returns the caption too:

```python
        spec = charts.parse_paperchart(code)
        charts.render_chart(spec, out_path)
        return Path(out_path), spec.title
```

`render/charts.py` — delete the two lines:

```python
    if spec.title:
        ax.set_title(spec.title)
```

- [ ] **Step 4: Run** full suite → all PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(v2.1): chart titles become Abbildung captions, not in-image titles"`

---

### Task 6: template `\paperhead` + caption setup + render() wiring

**Files:** Modify `render/templates/paper.latex`, `render/render_paper.py` (`render()`), `tests/test_render_paper.py`

- [ ] **Step 1: Failing test** (stub-render pipeline wiring):

```python
def test_render_pipeline_applies_styling_steps(tmp_path):
    md_text = (
        "# Titel\n\n**Anna Autor 1**\n**RWTH, Juni 2026**\n\n"
        "### Abstract\nKurz.  \nZweite Zeile.\n\n"
        "### Literaturverzeichnis\n1. Quelle Eins\n\n"
        "### Einleitung\nText.\n"
    )
    processed, _ = _render_with_stubs(
        tmp_path, md_text, authors="Anna Autor 1", dateline="RWTH, Juni 2026"
    )
    assert "Anna Autor 1" in processed.split("---")[1]   # only in frontmatter
    assert "**Anna Autor 1**" not in processed
    assert "# Einleitung" in processed                    # promoted H3→H1
    assert processed.rstrip().endswith("*[1] Quelle Eins*")
    assert "# Literaturverzeichnis {-}" in processed
    assert "abstract:" in processed and "Zweite Zeile." in processed
```

(`_render_with_stubs` already forwards kwargs to `rp.render`.)

- [ ] **Step 2: Run** → FAIL (steps not wired).
- [ ] **Step 3: Wire `render()`** — replace the transform block start with:

```python
    md = pre.strip_heading_numbers(md)
    extracted_title, md = pre.extract_title(md)
    abstract, md = pre.extract_abstract(md)
    md = pre.strip_author_lines(md, authors or "", dateline or "")
    md = pre.promote_headings(md)
    md = pre.move_references_last(md)
    md, _missing = pre.resolve_images(md, project_root)
```

and normalize the abstract for the single-box title head (rule 2):

```python
    meta = {
        "title": title or extracted_title or "",
        "author": authors or "",
        "dateline": dateline or "",
        "abstract": re.sub(r"\s+", " ", abstract).strip() if abstract else "",
    }
```

(add `import re` to the module imports).

- [ ] **Step 4: Template.** In `render/templates/paper.latex`:

After the `\providecommand{\pandocbounded}...` block add:

```latex
\usepackage{caption}
\captionsetup{font=footnotesize,labelfont=bf,labelsep=colon}
```

REPLACE the title/abstract machinery (the `\title{...}`, `\author{...}`, `\date{}` lines AND `\maketitle` + the `abstract` environment block inside the document) with:

```latex
\newcommand{\paperhead}{%
  \begin{center}
    {\LARGE $if(title)$$title$$else$\enspace$endif$\par}
    \vskip 0.9em
    $if(author)${\normalsize $author$\par}$endif$
    $if(dateline)${\normalsize $dateline$\par}$endif$
  \end{center}
  $if(abstract)$
  \vskip 0.6em
  {\itshape\leftskip=2em\rightskip=2em\noindent $abstract$\par}
  \vskip 1.2em
  $endif$
}

\begin{document}
$if(classoption)$
\twocolumn[{\paperhead}]
$else$
\paperhead
$endif$

$body$

\end{document}
```

- [ ] **Step 5: Compile regression both layouts** (real toolchain, proxy env set):

```python
@pytest.mark.skipif(rp.check_dependencies() != [], reason="render toolchain not installed")
@pytest.mark.parametrize("layout", ["one", "two"])
def test_template_compiles_both_layouts_with_styling(tmp_path, layout):
    md = tmp_path / "doc.md"
    md.write_text(
        "# Stiltest\n\n### Abstract\nKursive Kurzfassung.\n\n"
        "### Einleitung\nText mit Formel:\n\n$$E = m c^2$$\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n\n"
        "### Literaturverzeichnis\n1. Eine Quelle. Aachen.\n",
        encoding="utf-8",
    )
    out = tmp_path / f"doc-{layout}.pdf"
    rp.render(md, out, tmp_path, authors="Anna Autor 1", dateline="RWTH, Juni 2026",
              layout=layout, charts="off")
    assert out.read_bytes()[:5] == b"%PDF-"
```

- [ ] **Step 6: Run** full suite → all PASS.
- [ ] **Step 7: Commit** `git commit -m "feat(v2.1): paperhead title block, label-free italic abstract, caption setup, pipeline wiring"`

---

### Task 7: prompt lines, README, acceptance, wrap-up

**Files:** Modify `agents/make-paper.md`, `README.md`; reinstall agent; acceptance render.

- [ ] **Step 1: Agent prompt.** In `agents/make-paper.md` Step 6 PROMPT blockquote, append (always, not chart-conditional):

```
> Nenne den Abstract-Abschnitt exakt „Abstract" (englisches Wort, als
> Überschrift „### Abstract"). Beende das Paper mit einem Abschnitt
> „Literaturverzeichnis", der die tatsächlich verwendeten Quellen auflistet.
```

- [ ] **Step 2: Reinstall** `Copy-Item agents\make-paper.md $env:USERPROFILE\.claude\agents\make-paper.md -Force`.
- [ ] **Step 3: README.** Under "### v2: charts + two-column" add:

```markdown
### v2.1: styling rules

Always applied: label-free italic full-width abstract (named "Abstract");
authors/dateline only at the title block; references end the paper as
unnumbered "Literaturverzeichnis" with italic `[1] …` entries; display
formulas numbered `(1)`, `(2)`; table cells centered (H+V) in floats;
figures captioned "Abbildung N: <Titel>" (bold label, footnotesize);
sections numbered 1 / 1.1 / 1.1.1.
```

- [ ] **Step 4: Acceptance.** Re-render the live v2 paper with styling (proxy env in same invocation):

```powershell
python render/render_paper.py --input "F:\____IL_AI\test\Papers\Test Paper v2.md" --output "F:\____IL_AI\test\Papers\Test Paper v2.1.pdf" --project "F:\____IL_AI\test" --authors "Petr Nasybulin 478314, Philipp Gembruch 472685" --dateline "RWTH Aachen, Juni 2026" --layout two --charts auto
```

Verify in the PDF text: no "Zusammenfassung" label, authors appear exactly once, sections "1 ", "4.1 ", references last with "[1]", equations "(1)"/"(2)", captions "Abbildung 1:"/"Abbildung 2:". Open for the user.

- [ ] **Step 5: Full suite + CLEAR gate** → green/clean.
- [ ] **Step 6: Commit** `git add agents/make-paper.md README.md && git commit -m "feat(v2.1): prompt + docs for styling rules"`. Update session memory (main session).

---

## Self-review

- **Spec coverage:** rule 1 → T7 prompt + existing extract; rule 2 → T6 template+normalization; rule 3 → T1 + T6 wiring; rule 4 → T3 + T7 prompt; rule 5 → T4 Math; rule 6 → T4 Table (AlignCenter + m{}); rule 7 → T5 + T6 captionsetup; rule 8 → T2 + T6 wiring. Pipeline order documented in header. Error-handling: every step no-op tested (T1 noop tests, T2 noop, T3 noop).
- **Type consistency:** paperchart runner `(path, caption)|None` — preprocess (T5) and `run_paperchart` (T5) agree; autochart runner unchanged, caption via `getattr(spec, "title", "")`. `_HEADING` reused from existing preprocess module.
- **Placeholders:** none.
