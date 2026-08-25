"""Deterministic assertions. Free, repeatable, and blind to translation quality.

Four checks run on every case without being declared, because they encode the
output constraints that hold for all input. The declared assertions are the
per-case expectations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from slackchat.core.diffing import word_count
from slackchat.core.types import Limits, Mode, Result
from slackchat.core.validate import banned_chars_introduced, has_emoji

KNOWN_ASSERTIONS = frozenset(
    {"unchanged", "output_contains_any", "output_excludes", "max_changed_ratio", "max_words"}
)

_CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass(frozen=True)
class Case:
    id: str
    mode: Mode
    input: str
    asserts: dict[str, object]


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    passed: bool
    detail: str


def load_cases(directory: Path | None = None) -> list[Case]:
    """Load every ``*.yaml`` under ``directory``, sorted by filename then order."""
    target = directory if directory is not None else _CASES_DIR
    cases: list[Case] = []
    seen: dict[str, str] = {}
    for path in sorted(target.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for entry in entries:
            case_id = entry["id"]
            if case_id in seen:
                raise ValueError(
                    f"duplicate case id {case_id!r} in {path.name} and {seen[case_id]}"
                )
            seen[case_id] = path.name
            cases.append(
                Case(
                    id=case_id,
                    mode=entry["mode"],
                    input=entry["input"],
                    asserts=entry.get("assert") or {},
                )
            )
    return cases


def _universal(case: Case, result: Result, limits: Limits) -> list[CheckOutcome]:
    introduced = banned_chars_introduced(case.input, result.output, case.mode)
    in_words = word_count(case.input)
    out_words = word_count(result.output)
    ratio = out_words / in_words if in_words else 0.0
    return [
        CheckOutcome("no_emoji", not has_emoji(result.output), "emoji in output"),
        CheckOutcome(
            "no_banned_char_introduced",
            not introduced,
            f"introduced {' and '.join(introduced)}" if introduced else "",
        ),
        CheckOutcome("non_empty", bool(result.output.strip()), "output is empty"),
        CheckOutcome(
            "length_ratio",
            ratio <= limits.max_length_ratio,
            f"{out_words}/{in_words} words = {ratio:.2f} > {limits.max_length_ratio}",
        ),
    ]


def _declared(case: Case, result: Result) -> list[CheckOutcome]:
    unknown = set(case.asserts) - KNOWN_ASSERTIONS
    if unknown:
        raise ValueError(
            f"case {case.id}: unknown assertion(s) {sorted(unknown)}; "
            f"known: {sorted(KNOWN_ASSERTIONS)}"
        )

    outcomes: list[CheckOutcome] = []
    for name, expected in case.asserts.items():
        if name == "unchanged" and expected:
            # Trailing whitespace is stripped, the rest is byte-for-byte.
            passed = result.output.rstrip() == case.input.rstrip()
            outcomes.append(
                CheckOutcome("unchanged", passed, "" if passed else f"got {result.output!r}")
            )
        elif name == "output_contains_any":
            needles = cast(list[str], expected)
            passed = any(n in result.output for n in needles)
            outcomes.append(
                CheckOutcome(
                    "output_contains_any", passed, "" if passed else f"none of {list(needles)}"
                )
            )
        elif name == "output_excludes":
            excluded = cast(list[str], expected)
            hits = [n for n in excluded if n.lower() in result.output.lower()]
            outcomes.append(
                CheckOutcome("output_excludes", not hits, f"found {hits}" if hits else "")
            )
        elif name == "max_changed_ratio":
            passed = result.changed_ratio <= float(cast(Any, expected))
            outcomes.append(
                CheckOutcome(
                    "max_changed_ratio",
                    passed,
                    "" if passed else f"{result.changed_ratio} > {expected}",
                )
            )
        elif name == "max_words":
            words = word_count(result.output)
            passed = words <= int(cast(Any, expected))
            outcomes.append(
                CheckOutcome("max_words", passed, "" if passed else f"{words} > {expected}")
            )
    return outcomes


def check(case: Case, result: Result, limits: Limits) -> list[CheckOutcome]:
    """Every outcome for one case, universal checks first.

    A case-level ``max_changed_ratio`` applies to its own declared check only.
    The universal ``length_ratio`` check always uses the configured limit,
    because it guards a different thing (output ballooning) from a different
    direction (words, not tokens changed).
    """
    return _universal(case, result, limits) + _declared(case, result)
