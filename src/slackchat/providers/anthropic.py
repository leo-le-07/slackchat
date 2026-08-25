"""Anthropic provider. The only module in the project that talks to the API."""

from __future__ import annotations

from typing import Any

import anthropic

from slackchat.providers.base import Completion, ProviderError

DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    """Calls the Messages API once and returns plain text plus token counts.

    ``max_tokens`` is generous relative to the task (a chat message in, a chat
    message out) and small enough to stay well inside the SDK's non-streaming
    timeout. No ``thinking`` and no ``output_config.effort``: Haiku 4.5 takes
    neither, and ``effort`` is rejected outright.
    """

    name = "anthropic"

    def __init__(self, client: object | None = None, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        # Zero-arg construction resolves ANTHROPIC_API_KEY, then any other
        # configured credential source, from the environment. Typed as `Any`:
        # this is the one module allowed to touch the SDK's untyped surface.
        self._client: Any = client if client is not None else anthropic.Anthropic()
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, model: str) -> Completion:
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # wrapped so core/ never sees an SDK type
            raise ProviderError(str(exc)) from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            model=getattr(response, "model", model),
        )
