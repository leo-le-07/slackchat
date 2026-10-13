"""Golden cases for the correction prompt, and the hard checks run against them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from slackchat.core.detect import detect

DEFAULT_PATH = Path("evals/correction.yaml")
_KEYS = {"id", "group", "input", "reference", "include", "exclude", "max_changed_ratio"}
# "retried" is informational: the pipeline recovered from a violation.
_FAILING_FLAGS = frozenset(
    {"over_edit_suspected", "banned_char_introduced", "mechanical_fallback", "empty_output"}
)


@dataclass(frozen=True)
class Case:
    id: str
    group: Literal["unchanged", "needs_fix"]
    input: str
    reference: str | None = None
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    max_changed_ratio: float | None = None


def load_cases(path: Path = DEFAULT_PATH) -> list[Case]:
    if not path.exists():
        raise ValueError(f"case file not found: {path} (run from the project root)")
    cases: list[Case] = []
    seen: set[str] = set()
    for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
        cases.append(_parse(raw, seen))
    return cases


def _parse(raw: dict[str, Any], seen: set[str]) -> Case:
    cid = raw.get("id")
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"case without an id: {raw}")
    if unknown := set(raw) - _KEYS:
        raise ValueError(f"case {cid}: unknown key(s) {sorted(unknown)}")
    if cid in seen:
        raise ValueError(f"duplicate case id {cid}")
    seen.add(cid)
    group = raw.get("group")
    if group not in ("unchanged", "needs_fix"):
        raise ValueError(f"case {cid}: unknown group {group!r}")
    text = raw.get("input")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"case {cid}: input is empty")
    if group == "unchanged" and any(
        raw.get(k) for k in ("reference", "include", "exclude", "max_changed_ratio")
    ):
        raise ValueError(f"case {cid}: an unchanged case takes no other fields")
    if detect(text) != "correction":
        raise ValueError(f"case {cid}: input would run in translation mode")
    return Case(
        id=cid,
        group=group,
        input=text,
        reference=raw.get("reference"),
        include=tuple(raw.get("include", ())),
        exclude=tuple(raw.get("exclude", ())),
        max_changed_ratio=raw.get("max_changed_ratio"),
    )


def check(
    case: Case,
    *,
    output: str,
    changed_ratio: float | None,
    flags: list[str],
    error: str | None,
    default_max_ratio: float,
) -> list[str]:
    """Hard failures for one run. Empty list means pass."""
    if error:
        return [f"error: {error}"]
    failures = [f"flag: {f}" for f in flags if f in _FAILING_FLAGS]
    if len(output.splitlines()) != len(case.input.splitlines()):
        failures.append("line count changed")
    if case.group == "unchanged":
        if output.rstrip() != case.input.rstrip():
            failures.append("output differs from input")
        return failures
    failures += [f"missing {t!r}" for t in case.include if t not in output]
    failures += [f"still has {t!r}" for t in case.exclude if t in output]
    limit = case.max_changed_ratio if case.max_changed_ratio is not None else default_max_ratio
    if changed_ratio is not None and changed_ratio > limit:
        failures.append(f"changed_ratio {changed_ratio:.2f} > {limit:.2f}")
    return failures
