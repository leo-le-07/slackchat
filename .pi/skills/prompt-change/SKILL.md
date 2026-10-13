---
name: prompt-change
description: Edit a correction prompt in slackchat and check the new output against the golden set. Use whenever src/slackchat/prompts/*.md changes, or when Leo reports a bad real-world output and wants the prompt fixed.
---

# Changing a correction prompt (slackchat)

The golden set is `evals/correction.yaml`. `unchanged` cases must come back
byte-for-byte; `needs_fix` cases have hard `include`/`exclude` tokens plus a
soft `reference` diff. Needs `ANTHROPIC_API_KEY` (a few cents per run).

## Steps

1. **Baseline.** Note the current `version:` in the prompt. If
   `uv run slackchat eval --compare N N` says there are no eval runs for it,
   run `uv run slackchat eval` first. Without a baseline there is nothing to
   compare against.
2. **Edit the prompt and bump `version:`.** Never raise `max_changed_ratio`.
   Never edit or loosen an `unchanged` case to make a run pass.
3. **Run** `uv run slackchat eval`. A `WARNING: ... bump version:` means the
   text changed under an old version number; fix that before going on.
4. **Compare** `uv run slackchat eval --compare OLD NEW`. Exit 1 means an
   `unchanged` case regressed.
5. **Report to Leo, in this order:** `unchanged` regressions (blocker), cases
   that flipped (▼/▲), outputs that differ between versions with their diffs.
   Do not call the new prompt "better". Show the evidence and ask Leo to judge
   the diffs. One run per case is noisy: re-run before blaming a single flip.
6. **Done** when `./scripts/check.sh` exits 0. Commit with the `git-commit`
   skill.

## When Leo reports a bad output

Add it to `evals/correction.yaml` first (`needs_fix` with `include`/`exclude`
tokens that capture the fix, and a `reference`), run `uv run slackchat eval`
and watch it fail, then change the prompt. A prompt change without a case that
failed first is a guess.
