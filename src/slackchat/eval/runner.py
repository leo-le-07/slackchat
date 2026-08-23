"""Run the case suite, persist the outcomes, and compare prompt versions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from slackchat.eval.assertions import Case, check, load_cases
from slackchat.service import Service
from slackchat.store import sqlite as store

Out = Callable[[str], None]


@dataclass(frozen=True)
class RunSummary:
    passed: int
    total: int
    cost_usd: float
    unknown_cost_runs: int
    prompt_version: str


def run_suite(service: Service, *, cases: list[Case] | None = None, out: Out = print) -> RunSummary:
    """Run every case, record each check, and print a per-failure report."""
    suite = cases if cases is not None else load_cases()
    conn = store.connect()
    passed_cases = 0
    cost_total = 0.0
    unknown_cost = 0
    prompt_version = "?"
    try:
        for case in suite:
            result = service.run(case.input, case.mode, client="eval")
            prompt_version = result.prompt_version
            if result.cost_usd is None:
                unknown_cost += 1
            else:
                cost_total += result.cost_usd

            outcomes = check(case, result, service.config.limits)
            for outcome in outcomes:
                store.insert_eval_result(
                    conn,
                    run_id=result.run_id,
                    case_id=case.id,
                    check_name=outcome.name,
                    passed=outcome.passed,
                )
            failures = [o for o in outcomes if not o.passed]
            if failures:
                out(f"FAIL {case.id} ({case.mode})")
                out(f"     in : {case.input}")
                out(f"     out: {result.output}")
                for failure in failures:
                    out(f"     - {failure.name}: {failure.detail}")
                if result.flags:
                    out(f"     flags: {', '.join(result.flags)}")
            else:
                passed_cases += 1
    finally:
        conn.close()

    out("")
    out(f"pass rate {passed_cases}/{len(suite)} (prompt_version {prompt_version})")
    out(f"cost ${cost_total:.4f}")
    if unknown_cost:
        out(f"{unknown_cost} run(s) with unknown pricing, excluded from the total")
    return RunSummary(
        passed=passed_cases,
        total=len(suite),
        cost_usd=round(cost_total, 8),
        unknown_cost_runs=unknown_cost,
        prompt_version=prompt_version,
    )


def compare(version_a: str, version_b: str, *, out: Out = print) -> int:
    """Print the recorded pass rate for two prompt versions.

    The hash warning comes first on purpose: comparing two versions whose
    files were edited without a bump produces a number that looks meaningful
    and is not.
    """
    conn = store.connect()
    try:
        for version, hashes in store.prompt_hash_conflicts(conn):
            out(
                f"warning: prompt_version {version} was logged against {hashes} "
                f"different prompt hashes; runs under it are not comparable"
            )
        for version in (version_a, version_b):
            passed, total = store.pass_rate(conn, version)
            rate = f"{passed}/{total}" if total else "no runs"
            pct = f" ({passed / total:.0%})" if total else ""
            out(f"version {version}: {rate}{pct}")
    finally:
        conn.close()
    return 0
