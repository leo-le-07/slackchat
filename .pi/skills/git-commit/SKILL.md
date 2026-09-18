---
name: git-commit
description: Write git commit messages for the slackchat repo in the project's house style. Use whenever creating or amending a commit here, so subject lines and bodies stay consistent.
---

# Git commit messages (slackchat)

Keep every commit in this repo consistent with the style below.

## Before you commit

Run `./scripts/check.sh` — the single source of truth for the AGENTS.md check
order (ruff check, ruff format --check, mypy, pytest, lint-imports) — and
only commit if it exits 0.

If any step fails, fix it — do not commit around it.

## Subject line

Format: `type(scope): summary`

- **Prefix is required.** Use one of: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
- **Scope is optional.** Add it when the change is localized to one area:
  `cli`, `core`, `server`, `eval`, `store`, `providers`, `config`.
  Example: `feat(cli):`, `fix(core):`. Omit it for cross-cutting changes.
- Imperative mood: "add", "hide", "stop" — not "added" or "adds".
- Lowercase after the prefix. No trailing period.
- Aim for ~50 characters, hard cap ~72.

Good:
- `feat(cli): hide diff and changed-ratio for translation mode`
- `fix(cli): stop the REPL from splitting multi-paragraph pastes`
- `chore: add ruff and mypy, wire into CI`

Bad:
- `Add cli.show_status option to gate the status line` (no prefix, capitalized)
- `feat: Fixed the bug.` (past tense, capitalized, trailing period)

## Body

- Write a body when the change is non-trivial. Skip it only when the subject
  fully explains a small, obvious change.
- Blank line between subject and body.
- Wrap at ~72 characters.
- Explain **why**, not just what the diff already shows.
- **Contrast old vs. new behavior** — this is the house signature. State what
  the code did before and what it does now.
- Use a bullet list for multi-part changes; prose for a single change.

Example (why + contrast):

```
fix(cli): stop the REPL from splitting multi-paragraph pastes

A blank line submitted the buffer, so pasting text with a blank line
between paragraphs fired the turn on that blank line instead of on
Enter, chopping one paste into two runs.

Now two consecutive blank lines submit; a single blank line is kept as
a paragraph break.
```

## Never

- No secrets or `ANTHROPIC_API_KEY` values in messages.
- No "wip", "fix stuff", or other empty summaries.
- Do not loosen an eval `unchanged` case just to make a commit go green
  (see AGENTS.md).
