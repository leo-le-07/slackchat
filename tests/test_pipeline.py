import pytest

from slackchat.core.pipeline import process
from slackchat.core.prompts import Prompt
from slackchat.core.types import EmptyInputError
from slackchat.core.validate import (
    FLAG_BANNED_CHAR,
    FLAG_EMPTY_OUTPUT,
    FLAG_MECHANICAL,
    FLAG_OVER_EDIT,
    FLAG_RETRIED,
    FLAG_UNKNOWN_PRICING,
)

PROMPT = Prompt(mode="correction", version="7", text="SYSTEM PROMPT", hash="abcdef012345")


def run(provider, text, limits, **kwargs):
    from slackchat.providers.pricing import cost_usd

    kwargs.setdefault("cost_fn", cost_usd)
    kwargs.setdefault("prompt", PROMPT)
    kwargs.setdefault("model", "claude-haiku-4-5")
    kwargs.setdefault("clock", lambda: "2026-08-23T10:00:00Z")
    kwargs.setdefault("id_factory", lambda: "run0001")
    kwargs.setdefault("timer", iter([0.0, 0.25, 0.25, 0.60]).__next__)
    return process(text, provider=provider, limits=limits, **kwargs)


# --- happy paths ------------------------------------------------------------


def test_correction_of_a_real_error(fake_provider, limits):
    provider = fake_provider("I finished the task we discussed yesterday.")
    result = run(provider, "I has finish the task we discussed yesterday.", limits)
    assert result.output == "I finished the task we discussed yesterday."
    assert result.mode == "correction"
    assert result.flags == []
    assert result.changed_ratio == 0.25
    assert result.run_id == "run0001"
    assert result.created_at == "2026-08-23T10:00:00Z"
    assert result.latency_ms == 250
    assert result.prompt_version == "7"
    assert result.prompt_hash == "abcdef012345"
    assert result.provider == "fake"
    assert result.model == "claude-haiku-4-5"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cost_usd == pytest.approx(0.0002)
    assert result.error is None


def test_already_correct_text_comes_back_untouched(fake_provider, limits):
    text = "The deployment failed because the config was missing."
    result = run(fake_provider(text), text, limits)
    assert result.output == text
    assert result.changed_ratio == 0.0
    assert [c.kind for c in result.changes] == ["equal"]
    assert result.flags == []


def test_vietnamese_input_routes_to_translation(fake_provider, limits):
    provider = fake_provider("I finished the task yesterday.")
    result = run(provider, "Tôi đã hoàn thành task hôm qua.", limits)
    assert result.mode == "translation"


def test_the_user_message_is_the_input_text(fake_provider, limits):
    provider = fake_provider("some input")
    run(provider, "some input", limits)
    assert provider.calls[0]["user"] == "some input"
    assert provider.calls[0]["system"] == "SYSTEM PROMPT"


# --- empty input ------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_input_is_rejected_before_any_api_call(fake_provider, limits, text):
    provider = fake_provider(["should never be used"])
    with pytest.raises(EmptyInputError):
        run(provider, text, limits)
    assert provider.calls == []


# --- sanitize ---------------------------------------------------------------


def test_emoji_are_stripped_from_the_output(fake_provider, limits):
    provider = fake_provider("Looks good 👍")
    result = run(provider, "Looks good", limits)
    assert result.output == "Looks good"
    assert result.flags == []


# --- retry ------------------------------------------------------------------


def test_over_edit_triggers_one_retry_and_the_retry_wins(fake_provider, limits):
    provider = fake_provider(
        [
            "Unfortunately the deployment was unsuccessful due to a missing configuration file.",
            "The deployment failed because the config was missing.",
        ]
    )
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert len(provider.calls) == 2
    assert result.output == "The deployment failed because the config was missing."
    assert result.flags == [FLAG_RETRIED]
    assert result.latency_ms == 600  # both attempts counted


def test_the_retry_instruction_goes_on_the_user_message(fake_provider, limits):
    provider = fake_provider(["Deploy failed; rollback done.", "Deploy failed. Rollback done."])
    run(provider, "Deploy failed. Rollback done.", limits)
    first, second = provider.calls
    assert first["user"] == "Deploy failed. Rollback done."
    assert second["user"].startswith("Deploy failed. Rollback done.")
    assert "previous attempt was rejected" in second["user"]
    assert "semicolon" in second["user"]
    # The system prompt is untouched, so prompt_hash still identifies the prompt
    assert first["system"] == second["system"] == "SYSTEM PROMPT"


def test_persistent_over_edit_keeps_the_flag_after_the_retry(fake_provider, limits):
    bloated = "Unfortunately the deployment was unsuccessful due to a missing configuration file."
    provider = fake_provider([bloated, bloated])
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert len(provider.calls) == 2
    assert result.flags == [FLAG_OVER_EDIT, FLAG_RETRIED]
    assert result.output == bloated


def test_max_retries_zero_means_one_attempt(fake_provider, limits):
    from dataclasses import replace

    bloated = "Unfortunately the deployment was entirely unsuccessful for many reasons."
    provider = fake_provider([bloated])
    result = run(
        provider,
        "The deployment failed because the config was missing.",
        replace(limits, max_retries=0),
    )
    assert len(provider.calls) == 1
    assert result.flags == [FLAG_OVER_EDIT]
    assert FLAG_RETRIED not in result.flags


# --- mechanical fallback ----------------------------------------------------


def test_persistent_banned_char_falls_back_mechanically(fake_provider, limits):
    provider = fake_provider(["Deploy failed; rollback done.", "Deploy failed; rollback done."])
    result = run(provider, "Deploy failed. Rollback done.", limits)
    assert result.output == "Deploy failed, rollback done."
    assert result.flags == [FLAG_BANNED_CHAR, FLAG_OVER_EDIT, FLAG_RETRIED, FLAG_MECHANICAL]
    # the diff is recomputed against the substituted text
    assert result.changed_ratio == 0.5


def test_over_edit_alone_never_triggers_mechanical_substitution(fake_provider, limits):
    bloated = "Unfortunately the deployment was entirely unsuccessful for many reasons."
    provider = fake_provider([bloated, bloated])
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert FLAG_MECHANICAL not in result.flags


# --- empty output -----------------------------------------------------------


def test_empty_output_is_flagged_and_retried(fake_provider, limits):
    provider = fake_provider(["", ""])
    result = run(provider, "Some input here.", limits)
    assert result.flags == [FLAG_EMPTY_OUTPUT, FLAG_RETRIED]
    assert result.output == ""


# --- pricing ----------------------------------------------------------------


def test_unknown_pricing_sets_the_flag_and_a_null_cost(fake_provider, limits):
    provider = fake_provider("some input", model="some-local-llama")
    result = run(provider, "some input", limits)
    assert result.cost_usd is None
    assert result.flags == [FLAG_UNKNOWN_PRICING]


# --- provider failure -------------------------------------------------------


def test_provider_failure_becomes_a_result_with_an_error(fake_provider, limits):
    provider = fake_provider([], error="rate limited")
    result = run(provider, "I has finish the task.", limits)
    assert result.error == "rate limited"
    assert result.output == ""
    assert result.mode == "correction"
    assert result.cost_usd is None
    assert result.input_tokens is None
    assert result.run_id == "run0001"
