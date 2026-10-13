"""Run the golden set through the live prompt, and compare two prompt versions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

from slackchat.core.diffing import diff_words
from slackchat.core.prompts import load_prompt
from slackchat.eval.cases import Case, check
from slackchat.service import Service
from slackchat.store import sqlite as store

Out = Callable[[str], None]
_GROUPS = ("unchanged", "needs_fix")


def _diff(before: str, after: str) -> str:
    parts: list[str] = []
    for c in diff_words(before, after)[0]:
        if c.kind == "equal":
            parts.append(c.before)
        else:
            if c.before:
                parts.append(f"[-{c.before}-]")
            if c.after:
                parts.append(f"{{+{c.after}+}}")
    return " ".join(parts)


def _stale_hash_warning(conn: sqlite3.Connection, version: str, hash_: str) -> str | None:
    row = conn.execute(
        "SELECT 1 FROM runs WHERE client='eval' AND mode='correction' "
        "AND prompt_version=? AND prompt_hash!=? LIMIT 1",
        (version, hash_),
    ).fetchone()
    if row:
        return f"WARNING: prompt text changed but version is still {version}, bump version:"
    return None


def run_suite(service: Service, cases: list[Case], *, out: Out = print) -> int:
    """Exit code 1 if any `unchanged` case failed, else 0."""
    prompt = load_prompt("correction")
    conn = store.connect()
    try:
        warning = _stale_hash_warning(conn, prompt.version, prompt.hash)
    finally:
        conn.close()
    if warning:
        out(warning)

    ratio = service.config.limits.max_changed_ratio
    totals = {g: [0, 0] for g in _GROUPS}
    failed_unchanged = False
    soft: list[str] = []
    cost = 0.0
    for case in cases:
        result = service.run(case.input, client="eval")
        cost += result.cost_usd or 0.0
        failures = check(
            case,
            output=result.output,
            changed_ratio=result.changed_ratio,
            flags=result.flags,
            error=result.error,
            default_max_ratio=ratio,
        )
        totals[case.group][1] += 1
        if failures:
            out(f"FAIL {case.id}: {'; '.join(failures)}")
            failed_unchanged |= case.group == "unchanged"
        else:
            totals[case.group][0] += 1
        if (
            case.reference is not None
            and not result.error
            and result.output.rstrip() != case.reference.rstrip()
        ):
            soft.append(f"  {case.id}: {_diff(case.reference, result.output)}")

    out(f"prompt correction v{prompt.version} ({prompt.hash})")
    for g in _GROUPS:
        out(f"{g}: {totals[g][0]}/{totals[g][1]}")
    if soft:
        out("differs from reference (soft, judge by eye):")
        for line in soft:
            out(line)
    out(f"cost: ${cost:.4f}")
    return 1 if failed_unchanged else 0


def _latest(conn: sqlite3.Connection, version: str) -> tuple[dict[str, sqlite3.Row], set[str]]:
    rows = conn.execute(
        "SELECT input, output, changed_ratio, flags, error, prompt_hash FROM runs "
        "WHERE client='eval' AND mode='correction' AND prompt_version=? "
        "ORDER BY created_at, rowid",
        (version,),
    )
    by_input: dict[str, sqlite3.Row] = {}
    hashes: set[str] = set()
    for row in rows:
        by_input[row["input"]] = row  # later rows overwrite earlier ones
        hashes.add(row["prompt_hash"])
    return by_input, hashes


def compare(
    a: str, b: str, cases: list[Case], *, default_max_ratio: float, out: Out = print
) -> int:
    """Exit 1 if an `unchanged` case went pass -> fail, 2 if a version has no eval rows."""
    conn = store.connect()
    try:
        (rows_a, hashes_a), (rows_b, hashes_b) = _latest(conn, a), _latest(conn, b)
    finally:
        conn.close()
    for version, rows in ((a, rows_a), (b, rows_b)):
        if not rows:
            out(f"no eval runs for prompt version {version}; run `slackchat eval` on it first")
            return 2
    for version, hashes in ((a, hashes_a), (b, hashes_b)):
        note = " WARNING: several prompt texts under one version" if len(hashes) > 1 else ""
        out(f"v{version}: {', '.join(sorted(hashes))}{note}")

    def failures(case: Case, row: sqlite3.Row) -> list[str]:
        return check(
            case,
            output=row["output"],
            changed_ratio=row["changed_ratio"],
            flags=json.loads(row["flags"] or "[]"),
            error=row["error"],
            default_max_ratio=default_max_ratio,
        )

    counts = {g: [[0, 0], [0, 0]] for g in _GROUPS}  # group -> [[pass, total] for a, b]
    flips: list[str] = []
    changed: list[str] = []
    regressed = False
    for case in cases:
        ra, rb = rows_a.get(case.input), rows_b.get(case.input)
        for i, (version, row) in enumerate(((a, ra), (b, rb))):
            if row is None:
                out(f"{case.id}: not run in v{version}")
                continue
            counts[case.group][i][1] += 1
            counts[case.group][i][0] += not failures(case, row)
        if ra is None or rb is None:
            continue
        fa, fb = failures(case, ra), failures(case, rb)
        if not fa and fb:
            flips.append(f"▼ {case.id}: {'; '.join(fb)}")
            regressed |= case.group == "unchanged"
        elif fa and not fb:
            flips.append(f"▲ {case.id}")
        if ra["output"].rstrip() != rb["output"].rstrip():
            changed.append(f"  {case.id}: {_diff(ra['output'], rb['output'])}")

    out(f"{'':<12}v{a:<8}v{b}")
    for g in _GROUPS:
        (pa, ta), (pb, tb) = counts[g]
        out(f"{g:<12}{f'{pa}/{ta}':<9}{pb}/{tb}")
    out("\n".join(flips) if flips else "no case flipped")
    if changed:
        out(f"output differs between v{a} and v{b} (judge by eye):")
        out("\n".join(changed))
    return 1 if regressed else 0
