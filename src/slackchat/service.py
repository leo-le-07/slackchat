"""The one wiring layer. CLI and server both come through here.

``core/`` knows nothing about config files, price tables or the database.
This module knows about all three and about nothing else, which is what makes
"one shared core service" a property of the code rather than a claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from slackchat.config import Config, load_config
from slackchat.core.pipeline import process
from slackchat.core.prompts import Prompt, load_prompt
from slackchat.core.types import Mode, Result
from slackchat.providers.base import Provider
from slackchat.providers.pricing import cost_usd
from slackchat.store import sqlite as store


class UnknownProviderError(RuntimeError):
    """Raised when config names a provider that does not exist."""


def _build_provider(config: Config) -> Provider:
    if config.provider.name == "anthropic":
        from slackchat.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    raise UnknownProviderError(
        f"unknown provider {config.provider.name!r}; known providers: anthropic"
    )


@dataclass(frozen=True)
class Service:
    config: Config
    provider: Provider

    def run(self, text: str, mode: Mode | None = None, *, client: str) -> Result:
        """Process ``text``, log the outcome, return the Result.

        Logging lives here and nowhere else: ``core/`` must not know about a
        database, and duplicating the write per caller is how a caller ends up
        silently unlogged.
        """
        result = process(
            text,
            mode,
            provider=self.provider,
            limits=self.config.limits,
            model=self.config.provider.model,
            prompt=self._prompt_for(text, mode),
            cost_fn=cost_usd,
        )
        conn = store.connect()
        try:
            store.insert_run(conn, result, client=client)
        finally:
            conn.close()
        return result

    def _prompt_for(self, text: str, mode: Mode | None) -> Prompt | None:
        # Let the pipeline detect and load, unless the mode is already known.
        return load_prompt(mode) if mode is not None else None


def build_service(config: Config | None = None, provider: Provider | None = None) -> Service:
    resolved = config if config is not None else load_config()
    return Service(config=resolved, provider=provider or _build_provider(resolved))
