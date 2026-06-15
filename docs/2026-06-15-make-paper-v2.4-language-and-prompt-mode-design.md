# make-paper v2.4 — dialog language + NotebookLM-prompt mode

Date: 2026-06-15

Two main-session interaction features. Prose-only change to the agent
definition (`agents/make-paper.md`); no Python, no test changes. The subagent
still cannot ask the user anything — both new questions are asked by the **main
session** before delegation, like the existing profile/notebook/layout/charts
questions, and are encoded in the agent's `description` precondition.

## Feature 1 — dialog language (asked first, on its own)

Before any other question the main session asks, via `AskUserQuestion`:

```
In which language should we continue?
  1. English
  2. Deutsch
  3. Русский
```

The chosen language governs **all** subsequent main-session interaction:
the prompt-mode question, the profile/notebook/layout/charts questions, the
samples question, the graphics-review loop, the "Make DOCX?" question, and every
status/summary message.

It does **not** change the paper: the NotebookLM prompt and the generated paper
stay **German** (locked decision — output is always German). The language is
therefore main-session-only and is **not** passed to the subagent (which never
talks to the user).

## Feature 2 — NotebookLM-prompt mode (asked second)

After language, the main session asks, via `AskUserQuestion` (in the chosen
language):

```
How should I generate the prompt for NotebookLM?
  1. Default
  2. I already have my own prompt
  3. Let's discuss this
```

- **1 Default** — normal mode; the current default German content prompt is used.
- **2 I already have my own prompt** — the main session asks the user to provide
  it (paste a block in chat *or* give a file path; the main session loads the
  text). This becomes `PROMPT_OVERRIDE` and is passed to the subagent.
- **3 Let's discuss this** — the main session invokes the **grIL-me** skill as a
  free discussion to think the prompt through. grIL-me produces no automatic
  hand-off; when it ends, the main session **re-asks the prompt-mode question**,
  which then resolves to Default (1) or Own prompt (2).

## Prompt assembly (Step 6 of the subagent)

The NotebookLM prompt is built as `CONTENT + STRUCTURE`.

- `CONTENT`:
  - Default mode → the existing German "Schreibe ein wissenschaftliches
    Paper …/sample structure/tables" paragraph.
  - When `PROMPT_OVERRIDE` is present in the task prompt → that text **verbatim**,
    replacing only the content/topic part.
- `STRUCTURE` — **always appended in both modes**, so the renderer never breaks:
  1. German output regardless of source language; base content only on sources
     whose title does not start with "sample"; invent no data/values.
  2. Author line exactly `<author_names>`; institution line exactly `<dateline>`
     (title-block injection from the manifest — kept because the title block
     depends on it).
  3. Abstract section named exactly "Abstract", as `### Abstract`.
  4. End with a "Literaturverzeichnis" section listing the sources actually used.
  5. If charts were requested: the `paperchart` YAML-block rule.
  6. If samples are used (not ignored per the samples decision): take only the
     document structure/outline from the `sample*` sources.

This realizes the approved choice "replace content, keep structure rules": a
custom prompt governs *what* the paper is about, while the structural guarantees
the PDF/DOCX renderer relies on are always present.

## What changes

- `agents/make-paper.md`: `description` precondition gains the language and
  prompt-mode questions and the `PROMPT_OVERRIDE` task-prompt field; the body
  intro lists `PROMPT_OVERRIDE` as an optional input; Step 6 splits the prompt
  into `CONTENT` (default or override) + always-appended `STRUCTURE`.
- `README.md`: the "Use" section notes the two new questions.
- Reinstall the agent to `~/.claude/agents/make-paper.md`; commit + push.

## Out of scope

- No change to the renderer, helpers, charts, two-column logic, or DOCX path.
- The paper language stays German; this feature only localizes the operator
  dialog.
