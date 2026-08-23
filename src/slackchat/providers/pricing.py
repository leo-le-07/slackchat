"""Prices are data, not logic, so that a price change is a one-line edit.

Keys are the model ids the API returns in ``response.model``. As of
2026-08-23 that is the undated ``claude-haiku-4-5``; ``normalise_model_id``
strips a trailing date anyway, so a dated echo still costs correctly.
"""

from __future__ import annotations

import re

# model id -> (USD per 1M input tokens, USD per 1M output tokens)
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
}

_DATE_SUFFIX_RE = re.compile(r"-\d{8}\Z")
_PER_MILLION = 1_000_000


def normalise_model_id(model: str) -> str:
    return _DATE_SUFFIX_RE.sub("", model)


def cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Cost in USD, or ``None`` when it cannot be known.

    ``None`` rather than ``0.0`` on purpose: a zero here would be a lie
    inside the very data used to evaluate the tool.
    """
    if input_tokens is None or output_tokens is None:
        return None
    prices = PRICES_USD_PER_MTOK.get(normalise_model_id(model))
    if prices is None:
        return None
    in_price, out_price = prices
    total = (input_tokens * in_price + output_tokens * out_price) / _PER_MILLION
    return round(total, 8)
