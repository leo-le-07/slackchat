"""Data types shared across the whole system. No behaviour lives here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["correction", "translation"]
ChangeKind = Literal["equal", "insert", "delete", "replace"]


class EmptyInputError(ValueError):
    """Raised for empty or whitespace-only input, before any provider call."""


@dataclass(frozen=True)
class Change:
    """One word-level diff segment.

    ``equal`` segments are kept in ``Result.changes`` on purpose: they are what
    lets the CLI render an inline diff, and what lets the Phase 2 extension do
    the same from the JSON alone, without re-running the diff.
    """

    kind: ChangeKind
    before: str
    after: str


@dataclass(frozen=True)
class Limits:
    """Numeric gates. Lives in core so that core never imports config."""

    max_changed_ratio: float = 0.25
    max_length_ratio: float = 1.5
    max_retries: int = 1


@dataclass(frozen=True)
class Result:
    run_id: str
    original: str
    output: str
    mode: Mode
    forced: bool
    changes: list[Change]
    changed_ratio: float
    flags: list[str]
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    created_at: str
    error: str | None
