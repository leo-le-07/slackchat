# Eval harness + prompt-change skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After editing a correction prompt, one command re-runs a fixed golden set and one command compares two prompt versions, so a regression in "already-correct text comes back byte-for-byte" is caught before commit.

**Architecture:** `evals/correction.yaml` (golden set, repo root, cwd-relative like `data/`). `src/slackchat/eval/` loads cases, runs each through `Service.run(text, client="eval")` (so rows land in the existing `runs` table), and `--compare` re-derives pass/fail from the stored `runs` rows. No new table, no rubric, no review UI. Mode is `correction` only; `vi→en` is out of scope.

**Tech Stack:** existing only (`pyyaml` is still a dependency, `difflib` via `core.diffing`).

**Why smaller than before:** commit `1e1133b` removed an earlier eval suite (runner, `eval_results`, `reviews`, rubric, `--review`) as "more process than the project needs". This plan deliberately keeps only: dataset, run, compare. If a step starts to look like the old suite, stop and cut it.

## Global Constraints

- Tests never hit the network: inject `FakeProvider` (`tests/conftest.py`), use `isolated_paths`.
- `core/` and `providers/` must not import `slackchat.eval` (re-add it to both `forbidden_modules` lists in `pyproject.toml`; the import-linter contract was edited out in `1e1133b`).
- Model/prompt rules from AGENTS.md apply: never raise `max_changed_ratio` to make a case pass; never loosen an `unchanged` case to go green; fix = tighter prompt + bumped `version:`.
- Done = `./scripts/check.sh` exits 0.

## Decisions already made (from the user)

- `unchanged` group = the 11 examples in `notes.md` (text before `# Voice Constraint`).
- `needs_fix` group = mined from `data/runs.db` (`mode='correction'`, distinct `input`), built by the agent, reviewed once by the user.
- `vi→en`: not now.

## Open decision for the user (gate in Task 3)

Several of the 11 `notes.md` examples contain real errors under prompt v5's own rule "sửa lỗi ngữ pháp" (e.g. Ex.2 `okey` / `add more a`, Ex.5 `Will keep you updates`, Ex.9 `bigger then`, Ex.11 `if we not priority`, Ex.7 `I have interview`). Taken byte-exact as `unchanged`, v5 will "fail" them by design. Plan: load them verbatim, run the baseline, then the user decides per failing case: (a) it really is acceptable as-is → stays `unchanged` (prompt over-edits), or (b) it has a typo → move to `needs_fix` with a corrected `reference`. The agent must not decide this alone.

## Case format (`evals/correction.yaml`)

```yaml
- id: keep-01              # unchanged: hard check = output == input (trailing whitespace stripped)
  group: unchanged
  input: |-
    Regarding the Dental Project, ...

- id: fix-01               # needs_fix
  group: needs_fix
  input: "...achivements..."
  reference: "...achievements..."   # approved output, SOFT: shown as a diff when output differs, never fails
  include: ["achievements"]          # HARD: each must appear in output
  exclude: ["achivements"]           # HARD: none may appear in output
  max_changed_ratio: 0.35            # optional, defaults to config limit
```

Hard checks for every case (shared): no `error`; none of the flags `over_edit_suspected`, `banned_char_introduced`, `mechanical_fallback`, `empty_output` (`retried` is info only); output line count == input line count. `include`/`exclude` are 1–3 decisive tokens per case chosen by hand, not the whole sentence: the rest is `reference`, judged by the user's eyes.

## File Structure

- Create `evals/correction.yaml` — golden set.
- Create `src/slackchat/eval/__init__.py` (empty).
- Create `src/slackchat/eval/cases.py` — `Case`, `load_cases`, `check`.
- Create `src/slackchat/eval/runner.py` — `run_suite`, `compare`.
- Modify `src/slackchat/cli/main.py` — `eval` subcommand.
- Modify `pyproject.toml` — add `slackchat.eval` to both forbidden lists.
- Modify `AGENTS.md` — commands + one rule line.
- Create `.pi/skills/prompt-change/SKILL.md`.
- Tests: `tests/test_eval_cases.py`, `tests/test_eval_runner.py`.

---

### Task 1: Case model, loader, and `check`

**Files:** Create `src/slackchat/eval/__init__.py`, `src/slackchat/eval/cases.py`; Test `tests/test_eval_cases.py`.

**Interfaces:**
- Produces:
  - `Case(id: str, group: Literal["unchanged","needs_fix"], input: str, reference: str | None, include: tuple[str, ...], exclude: tuple[str, ...], max_changed_ratio: float | None)` — frozen dataclass
  - `load_cases(path: Path = Path("evals/correction.yaml")) -> list[Case]` — raises `ValueError` on: duplicate id, unknown group, unknown key, `unchanged` with `reference`/`include`/`exclude`, `needs_fix` with empty input, or `detect(input) != "correction"` (a case that would silently run in translation mode)
  - `check(case: Case, *, output: str, changed_ratio: float | None, flags: list[str], error: str | None, default_max_ratio: float) -> list[str]` — returns failure messages, empty = pass

- [ ] **Step 1: Write failing tests** — one per rule: unchanged pass/fail (trailing-whitespace tolerated, a changed byte fails), include missing, exclude present, flag `over_edit_suspected` fails but `retried` does not, line-count mismatch, `error` set, ratio over the case's / default limit, and each `load_cases` rejection above (use `tmp_path` YAML).
- [ ] **Step 2: Run** `uv run pytest tests/test_eval_cases.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** minimal `cases.py`. Reuse `core.detect.detect`; no new helpers beyond these three names.
- [ ] **Step 4: Run** the test file → PASS.
- [ ] **Step 5: Commit** (`git-commit` skill): `feat(eval): add case model, loader and checks`.

---

### Task 2: Runner, compare, and the `eval` CLI

**Files:** Create `src/slackchat/eval/runner.py`; Modify `src/slackchat/cli/main.py`, `pyproject.toml`; Test `tests/test_eval_runner.py`.

**Interfaces:**
- Consumes: `Service.run(text, client="eval") -> Result`, `store.connect()`, `core.diffing.diff_words`, Task 1 names.
- Produces:
  - `run_suite(service: Service, cases: list[Case], *, out=print) -> int` — runs every case, prints per-group `passed/total`, each failure (`id: message`), cases whose output differs from `reference` (word diff, labelled "soft"), total cost, and the prompt `version`/`hash`. Returns exit code: `1` if any `unchanged` case failed, else `0`.
  - `compare(a: str, b: str, cases: list[Case], *, default_max_ratio: float, out=print) -> int` — for each version, take the **latest** `runs` row per `input` where `client='eval' AND mode='correction' AND prompt_version=?`, re-run `check` on the stored columns (`output`, `changed_ratio`, `flags` JSON, `error`), then print: per-group pass count for A and B; cases that flipped pass→fail (▼) or fail→pass (▲); cases whose output text differs between A and B with a word diff. Cases missing from a version are listed as "not run in X". Returns `1` if any `unchanged` case went pass→fail, else `0`.
- CLI: `slackchat eval` (run on the current prompt), `slackchat eval --compare 5 6`. `eval` goes into `SUBCOMMANDS` and `main()` routing like `log`. `--compare` needs no API key.
- Stale-version guard: `run_suite` queries `runs` for an earlier eval row with the same `prompt_version` but a different `prompt_hash` and prints `WARNING: prompt text changed but version is still N, bump version:`. This catches the known "edited, forgot to bump" failure.

- [ ] **Step 1: Write failing tests** with `FakeProvider` + `isolated_paths`: (a) suite passes on an echo provider for an `unchanged` case; (b) a provider that alters one word makes the `unchanged` case fail and `run_suite` return 1; (c) two runs under different `prompt_version` values (pass a prompt object/monkeypatch `load_prompt`, as `tests/test_service.py` does) then `compare` shows a ▼ and returns 1; (d) same version, different hash → warning printed; (e) `compare` with a version that has no eval rows prints a clear message and returns 2, not a traceback.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `runner.py`, wire the CLI, add `slackchat.eval` to both `forbidden_modules` lists.
- [ ] **Step 4: Run** `uv run pytest tests/test_eval_runner.py -q && uv run lint-imports` → PASS.
- [ ] **Step 5: Commit**: `feat(eval): add eval run and version compare`.

---

### Task 3: Build the golden set

**Files:** Create `evals/correction.yaml`. No code is committed from this task.

- [ ] **Step 1: `unchanged` from notes.** Split `notes.md` on `^Example \d+:?\s*$` up to `# Voice Constraint`; 11 blocks, keep inner newlines (Ex.3 and Ex.8 are multi-line), strip the outer blank lines only. IDs `keep-01..11`, YAML block scalar `|-`.
- [ ] **Step 2: `needs_fix` from the DB** (throwaway script, not committed). From `data/runs.db`: `mode='correction' AND error IS NULL AND client!='eval'`, group by `input`, keep the newest row. 92 rows / 85 distinct inputs today. Drop: inputs equal to any `keep-*` input, empty or whitespace-only outputs, inputs where newest `output.strip() == input.strip()` (they are `unchanged` candidates, ask the user before adding). Cap at about 40, preferring inputs with a real error (typo, grammar, missing capital) over pure fluency rewrites.
- [ ] **Step 3: Draft `reference`.** Use the user's verdicts in `data/replay_results.md` (`Nhận xét:` lines) for the 29 inputs also in the DB: ✓ → the v4 output is the reference; a comment that asks for a change (capitalise first letter, no `-`) → apply it to the reference. Everything else: newest DB output, marked `# unreviewed` in a YAML comment.
- [ ] **Step 4: Pick `include`/`exclude`** by hand from the diff input→reference: only unambiguous fixes (`achivements`→`achievements`, `okey`→`okay`). Fluency rewrites get none, so they rely on the shared checks plus the `reference` diff.
- [ ] **Step 5: Validate** `uv run python -c "from slackchat.eval.cases import load_cases; print(len(load_cases()))"` → prints the count, no error.
- [ ] **Step 6: User review gate.** Show the user the YAML diff and every `# unreviewed` case. Do not proceed to Step 7 until they approve.
- [ ] **Step 7: Commit**: `feat(eval): add the correction golden set`.

---

### Task 4: Baseline run and the `unchanged` triage

- [ ] **Step 1:** `uv run slackchat eval` on the current prompt (v5). Needs `ANTHROPIC_API_KEY`; about 50 haiku calls, a few cents.
- [ ] **Step 2:** For every failing `keep-*` case, show the user input vs output and the open decision above. Apply their verdict: edit the YAML (move to `needs_fix` with a corrected `reference`, or leave it and record that v5 over-edits it).
- [ ] **Step 3:** Re-run `uv run slackchat eval` and note the v5 baseline pass counts in the commit body. The baseline rows in `runs` are what Task 5's `--compare` will diff against.
- [ ] **Step 4: Commit** any YAML change: `test(eval): settle the unchanged baseline`.

---

### Task 5: The `prompt-change` skill and AGENTS.md

**Files:** Create `.pi/skills/prompt-change/SKILL.md`; Modify `AGENTS.md`.

- [ ] **Step 1: Write the skill** (about 30 lines, same frontmatter style as `git-commit`). Trigger: any edit to `src/slackchat/prompts/*.md`, or "update the prompt". Steps:
  1. Before touching the prompt, make sure eval rows exist for the current version; if not, run `uv run slackchat eval` first. That is the baseline `--compare` needs.
  2. Edit the prompt and bump `version:`. Never change `max_changed_ratio`; never edit or loosen an `unchanged` case.
  3. `uv run slackchat eval`, then `uv run slackchat eval --compare OLD NEW`.
  4. Report to the user, in this order: `unchanged` regressions (blocker), flipped cases, outputs that changed with their diffs. Do not call the new prompt "better": present the evidence and ask the user to judge the soft diffs.
  5. When the user reports a bad real-world output: add it as a `needs_fix` case first, run `eval` to see it fail, then change the prompt.
  6. `./scripts/check.sh`, then commit with the `git-commit` skill.
- [ ] **Step 2: AGENTS.md** — add under Commands `- Eval: uv run slackchat eval` and `- Compare prompt versions: uv run slackchat eval --compare 5 6`; add one line to "The constraint that matters": the `unchanged` cases in `evals/correction.yaml` measure this, and are never loosened to go green; point prompt edits at the `prompt-change` skill.
- [ ] **Step 3:** `./scripts/check.sh` → exit 0.
- [ ] **Step 4: Commit**: `docs: add prompt-change skill and eval commands`.

---

## Review Focus

- A prompt edited without a `version:` bump → the Task 2 hash warning.
- LLM nondeterminism: one run per case per version, so a single flip can be noise. Re-run `eval` before blaming the prompt. `--repeat N` is not built.
- Eval rows (`client='eval'`) now appear in `slackchat log` and in future DB mining. Task 3's query already excludes them; `log` is left as is.
- `evals/` is read relative to the working directory, same as `data/runs.db`. Running from another directory fails with a clear "file not found" from `load_cases`, not a traceback.
- Multi-line inputs (23 of 92 DB inputs) round-trip through YAML `|-` without gaining or losing a trailing newline.

## Not in this plan

`vi→en` cases, the 0/1/2 rubric, human review CLI, LLM judge, `--repeat`, deleting `scripts/replay.py` and `data/replay_*` (superseded by `eval`; the user decides).
