"""``process()`` — the single entry point of the whole system.

The CLI renders what this returns. The server serialises it. The eval runner
asserts on it. There is deliberately no second code path.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from slackchat.core.detect import detect
from slackchat.core.diffing import diff_words
from slackchat.core.prompts import Prompt, load_prompt
from slackchat.core.types import Change, EmptyInputError, Limits, Mode, Result
from slackchat.core.validate import (
    FLAG_BANNED_CHAR,
    FLAG_MECHANICAL,
    FLAG_RETRIED,
    FLAG_UNKNOWN_PRICING,
    Violation,
    find_violations,
    mechanical_replace,
    retry_suffix,
    sanitize,
)
from slackchat.providers.base import Completion, Provider, ProviderError


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _dedupe(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            ordered.append(flag)
    return ordered


def process(
    text: str,
    mode: Mode | None = None,
    *,
    provider: Provider,
    limits: Limits,
    model: str,
    prompt: Prompt | None = None,
    cost_fn: Callable[[str, int | None, int | None], float | None] | None = None,
    clock: Callable[[], str] | None = None,
    id_factory: Callable[[], str] | None = None,
    timer: Callable[[], float] | None = None,
) -> Result:
    """Detect, prompt, complete, sanitize, diff, validate, retry once, return.

    ``cost_fn`` is injected, never imported: ``core/`` may not reach
    ``providers.pricing`` (contract 2, and ``import-linter`` sees function-level
    imports too, so a lazy import would not dodge it). With no ``cost_fn`` the
    cost is unknown, which is the honest default for a caller that did not
    supply a price table. ``service.py`` always supplies one.
    """
    if not text.strip():
        raise EmptyInputError("input is empty or whitespace only")

    if cost_fn is None:

        def cost_fn(_model: str, _in_tokens: int | None, _out_tokens: int | None) -> float | None:  # noqa: ARG001
            return None

    clock = clock or _utc_now
    id_factory = id_factory or _new_id
    timer = timer or time.monotonic

    resolved_mode: Mode = mode if mode is not None else detect(text)
    forced = mode is not None
    active_prompt = prompt if prompt is not None else load_prompt(resolved_mode)

    run_id = id_factory()
    created_at = clock()

    elapsed = 0.0
    attempt = 0
    suffix = ""
    flags: list[str] = []
    completion: Completion | None = None
    output = ""
    changes: list[Change] = []
    changed_ratio = 0.0

    while True:
        started = timer()
        try:
            completion = provider.complete(active_prompt.text, text + suffix, model=model)
        except ProviderError as exc:
            return Result(
                run_id=run_id,
                original=text,
                output="",
                mode=resolved_mode,
                forced=forced,
                changes=[],
                changed_ratio=0.0,
                flags=_dedupe(flags),
                provider=provider.name,
                model=model,
                prompt_version=active_prompt.version,
                prompt_hash=active_prompt.hash,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=int(round((elapsed + (timer() - started)) * 1000)),
                created_at=created_at,
                error=str(exc),
            )
        elapsed += timer() - started

        output = sanitize(completion.text)
        changes, changed_ratio = diff_words(text, output)
        violations = find_violations(
            original=text,
            output=output,
            mode=resolved_mode,
            changed_ratio=changed_ratio,
            max_changed_ratio=limits.max_changed_ratio,
        )

        if not violations or attempt >= limits.max_retries:
            flags.extend(v.flag for v in violations)
            if attempt > 0:
                flags.append(FLAG_RETRIED)
            output, changes, changed_ratio = _apply_last_resort(
                violations, text, output, changes, changed_ratio, flags
            )
            break

        attempt += 1
        suffix = retry_suffix(violations)

    # TODO: refactor to prevent calling cost_fn twice
    if cost_fn(completion.model, completion.input_tokens, completion.output_tokens) is None:
        flags.append(FLAG_UNKNOWN_PRICING)
    cost = cost_fn(completion.model, completion.input_tokens, completion.output_tokens)

    return Result(
        run_id=run_id,
        original=text,
        output=output,
        mode=resolved_mode,
        forced=forced,
        changes=changes,
        changed_ratio=changed_ratio,
        flags=_dedupe(flags),
        provider=provider.name,
        model=completion.model,
        prompt_version=active_prompt.version,
        prompt_hash=active_prompt.hash,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        cost_usd=cost,
        latency_ms=int(round(elapsed * 1000)),
        created_at=created_at,
        error=None,
    )


def _apply_last_resort(
    violations: list[Violation],
    original: str,
    output: str,
    changes: list[Change],
    changed_ratio: float,
    flags: list[str],
) -> tuple[str, list[Change], float]:
    """Substitute banned characters mechanically, and only those.

    Over-edit gets no mechanical remedy: there is no safe machine way to undo
    a rewrite, so it is reported as a flag and the output is returned as-is.
    """
    if not any(v.flag == FLAG_BANNED_CHAR for v in violations):
        return output, changes, changed_ratio
    replaced = mechanical_replace(output)
    if replaced == output:
        return output, changes, changed_ratio
    flags.append(FLAG_MECHANICAL)
    new_changes, new_ratio = diff_words(original, replaced)
    return replaced, new_changes, new_ratio
