"""The provider seam. ``core/`` depends on this module and nothing else here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """Any provider-side failure, with the SDK exception as ``__cause__``.

    Providers wrap their SDK's exceptions in this so that ``core/`` can catch
    a failure without importing a vendor SDK.
    """


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    model: str


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, model: str) -> Completion: ...
