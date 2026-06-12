"""Pure Markdown transforms for make-paper Subsystem B. No external processes."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_HEADING_NUM = re.compile(r"^(#{1,6})\s+\d+(?:\.\d+)*\.?\s+(.*\S)\s*$")


def strip_heading_numbers(md: str) -> str:
    """Remove a leading section number (e.g. '2.' or '2.3') from ATX headings."""
    out = []
    for line in md.splitlines():
        m = _HEADING_NUM.match(line)
        out.append(f"{m.group(1)} {m.group(2)}" if m else line)
    return "\n".join(out)


_H1 = re.compile(r"^#\s+(.*\S)\s*$")


def extract_title(md: str) -> tuple[str | None, str]:
    """Return (title, body_without_title). Title = first level-1 ATX heading."""
    lines = md.splitlines()
    for i, line in enumerate(lines):
        m = _H1.match(line)
        if m:
            del lines[i]
            return m.group(1), "\n".join(lines)
    return None, md


_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_ABSTRACT_TITLES = {"abstract", "zusammenfassung", "kurzfassung"}


def extract_abstract(md: str) -> tuple[str | None, str]:
    """Pull out a leading Abstract/Zusammenfassung/Kurzfassung section.

    Returns (abstract_text, body_without_that_section). The abstract spans from
    just after its heading to the next heading of the same or higher level.
    """
    lines = md.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m and m.group(2).strip().lower() in _ABSTRACT_TITLES:
            start, level = i, len(m.group(1))
            break
    if start is None:
        return None, md
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING.match(lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    abstract = "\n".join(lines[start + 1:end]).strip()
    body = "\n".join(lines[:start] + lines[end:]).strip("\n")
    return abstract, body


_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def resolve_images(md: str, project_root: Path) -> tuple[str, list[str]]:
    """Rewrite relative Markdown image targets to absolute project paths.

    Returns (rewritten_md, missing_targets). URLs and absolute paths are kept;
    missing relative targets are recorded and left unchanged.
    """
    missing: list[str] = []

    def repl(m: re.Match) -> str:
        alt, target = m.group(1), m.group(2).strip()
        if target.startswith(("http://", "https://")) or Path(target).is_absolute():
            return m.group(0)
        candidate = (project_root / target).resolve()
        if candidate.is_file():
            return f"![{alt}]({candidate.as_posix()})"
        missing.append(target)
        return m.group(0)

    return _IMG.sub(repl, md), missing


_MERMAID = re.compile(r"^```mermaid[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)


def iter_mermaid_blocks(md: str) -> list[str]:
    """Return the code body of each ```mermaid fenced block, in order."""
    return [m.group(1) for m in _MERMAID.finditer(md)]


def render_mermaid_blocks(md: str, out_dir: Path, runner, ext: str = "pdf") -> str:
    """Replace each ```mermaid block with an image link, rendering via `runner`.

    `runner(code: str, out_path: Path) -> None` produces an image file at
    out_path. `ext` picks the figure format (pdf for LaTeX, png for docx).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def repl(m: re.Match) -> str:
        code = m.group(1)
        digest = hashlib.sha1(code.encode("utf-8")).hexdigest()[:12]
        out_path = out_dir / f"mermaid-{digest}.{ext}"
        runner(code, out_path)
        return f"![]({out_path.as_posix()})"

    return _MERMAID.sub(repl, md)


_LETTERS_ONLY = re.compile(r"[^A-Za-zÄÖÜäöüß]")
_LABEL_RESIDUE = 24   # letters a label like "Autoren:"/"Institution:" can have


def _author_targets(authors: str, dateline: str) -> list[str]:
    """Substrings that mark a line as author/institution info, longest first."""
    targets = {" ".join(t.split()) for t in (authors, dateline) if t and t.strip()}
    for part in (authors or "").split(","):
        name = " ".join(part.split())
        if name:
            targets.add(name)
            bare = re.sub(r"[\s\d]+$", "", name)   # without matriculation number
            if bare:
                targets.add(bare)
    if dateline and "," in dateline:
        inst = dateline.split(",", 1)[0].strip()
        if inst:
            targets.add(inst)
    return sorted(targets, key=len, reverse=True)


def strip_author_lines(md: str, authors: str, dateline: str) -> str:
    """Drop pre-heading lines carrying author or institution info.

    The title block already shows authors + dateline (styling rule 3), but
    NotebookLM repeats them below the abstract in varying shapes ("Autoren:
    P. N. (478314) …", "**Institution:** RWTH Aachen"). A line is dropped
    when removing every matched target leaves at most a short label, so real
    sentences that merely mention the institution survive. Only the region
    BEFORE the first ATX heading is touched.
    """
    targets = _author_targets(authors, dateline)
    if not targets:
        return md
    out = []
    removed = False
    seen_heading = False
    for line in md.splitlines():
        if _HEADING.match(line):
            seen_heading = True
        if not seen_heading:
            content = " ".join(line.replace("*", "").replace("_", "").split())
            residue = content
            for t in targets:
                residue = residue.replace(t, "")
            if (content and residue != content
                    and len(_LETTERS_ONLY.sub("", residue)) <= _LABEL_RESIDUE):
                removed = True
                continue
        out.append(line)
    if not removed:
        return md
    return "\n".join(out) + ("\n" if md.endswith("\n") else "")


def promote_headings(md: str) -> str:
    """Uniformly shift ATX headings so the smallest level present becomes 1.

    Gives --number-sections the 1 / 1.1 / 1.1.1 scheme (styling rule 8).
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


_REF_TITLES = {"literaturverzeichnis", "literatur", "quellen", "referenzen"}
_REF_ENTRY = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+(.*\S)\s*$")


def move_references_last(md: str) -> str:
    """Move the references section to the end; entries become '*[n] …*'.

    The section is retitled to an unnumbered '# Literaturverzeichnis {-}'
    (styling rule 4). Recognized titles: Literaturverzeichnis, Literatur,
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
    # trailing backslash = pandoc hard line break, so each entry starts a new line
    out += [f"*[{n}] {text}*" + ("\\" if n < len(entries) else "")
            for n, text in enumerate(entries, 1)]
    return "\n".join(out) + "\n"


_PAPERCHART = re.compile(r"^```paperchart[ \t]*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)


def render_paperchart_blocks(md: str, out_dir: Path, runner,
                             ext: str = "pdf") -> tuple[str, int]:
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
        result = runner(code, out_dir / f"chart-{digest}.{ext}")
        if not result:
            return ""
        path, caption = result
        return f"![{caption}]({Path(path).as_posix()})"

    return _PAPERCHART.sub(repl, md), count


def inject_autodetected_charts(md: str, out_dir: Path, runner, detect,
                               ext: str = "pdf") -> str:
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
        result = runner(spec, out_dir / f"autochart-{n:02d}.{ext}")
        if result:
            caption = getattr(spec, "title", "") or ""
            lines[end_idx + 1:end_idx + 1] = ["", f"![{caption}]({Path(result).as_posix()})"]
    return "\n".join(lines)


def _yaml_scalar(value: str) -> str:
    """Double-quote a YAML scalar, escaping backslashes and quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_frontmatter(meta: dict) -> str:
    """Build a Pandoc YAML metadata block from title/author/dateline/abstract.

    Empty fields are omitted; abstract uses a literal block scalar.
    """
    lines = ["---"]
    for key in ("title", "author", "date", "dateline"):
        if meta.get(key):
            lines.append(f"{key}: {_yaml_scalar(meta[key])}")
    if meta.get("abstract"):
        lines.append("abstract: |")
        for ln in meta["abstract"].splitlines():
            lines.append("  " + ln)
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
