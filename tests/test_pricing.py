from slackchat.providers.pricing import (
    PRICES_USD_PER_MTOK,
    cost_usd,
    normalise_model_id,
)


def test_haiku_is_in_the_table_at_one_and_five():
    assert PRICES_USD_PER_MTOK["claude-haiku-4-5"] == (1.00, 5.00)


def test_undated_id_resolves():
    assert normalise_model_id("claude-haiku-4-5") == "claude-haiku-4-5"


def test_dated_id_normalises_to_the_undated_key():
    # Defensive: if the API ever echoes a dated id, cost must still be right.
    assert normalise_model_id("claude-haiku-4-5-20251001") == "claude-haiku-4-5"


def test_a_trailing_non_date_suffix_is_left_alone():
    assert normalise_model_id("claude-haiku-4-5-preview") == "claude-haiku-4-5-preview"


def test_cost_of_a_known_model():
    # 1000 input at $1/MTok + 400 output at $5/MTok
    assert cost_usd("claude-haiku-4-5", 1000, 400) == 0.003


def test_cost_of_a_dated_known_model():
    assert cost_usd("claude-haiku-4-5-20251001", 1000, 400) == 0.003


def test_unknown_model_is_none_never_zero():
    assert cost_usd("some-local-llama", 1000, 400) is None


def test_missing_token_counts_are_none_never_zero():
    assert cost_usd("claude-haiku-4-5", None, 400) is None
    assert cost_usd("claude-haiku-4-5", 1000, None) is None


def test_zero_tokens_is_a_real_zero():
    assert cost_usd("claude-haiku-4-5", 0, 0) == 0.0
