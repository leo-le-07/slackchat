"""Terminal rendering. Knows nothing about the pipeline beyond ``Result``."""

from __future__ import annotations

from slackchat.core.types import Change, Result

RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
DIM = "\x1b[2m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_inline_diff(changes: list[Change], *, color: bool) -> str:
    """One line showing what moved.

    Without colour the markers are ``[-removed-]`` and ``{+added+}`` so that a
    redirected run is still readable, and so that a screenshot in a bug report
    survives losing its escape codes.
    """
    parts: list[str] = []
    for change in changes:
        if change.kind == "equal":
            parts.append(change.before)
            continue
        chunk = ""
        if change.before:
            chunk += _paint(change.before, RED, color) if color else f"[-{change.before}-]"
        if change.after:
            chunk += _paint(change.after, GREEN, color) if color else f"{{+{change.after}+}}"
        if chunk:
            parts.append(chunk)
    return " ".join(p for p in parts if p)


def _meta_line(result: Result) -> str:
    cost = f"${result.cost_usd:.6f}" if result.cost_usd is not None else "cost n/a"
    mode = f"{result.mode} (forced)" if result.forced else result.mode
    return " · ".join(
        [
            mode,
            f"changed {round(result.changed_ratio * 100)}%",
            result.model,
            f"{result.latency_ms}ms",
            cost,
        ]
    )


def render_result(result: Result, *, color: bool) -> str:
    """The human view: clean output, then how it got there."""
    lines = [result.output, ""]
    if result.error:
        lines.append(_paint(f"error: {result.error}", RED, color))
        return "\n".join(lines).rstrip() + "\n"

    lines.append(_paint(f"  {_meta_line(result)}", DIM, color))
    lines.append(f"  {render_inline_diff(result.changes, color=color)}")
    if result.flags:
        lines.append(_paint(f"  flags: {', '.join(result.flags)}", RED, color))
    return "\n".join(lines) + "\n"
