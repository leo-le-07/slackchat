from slackchat.cli.render import render_inline_diff, render_result
from slackchat.core.types import Change, Result

RED = "\x1b[31m"
GREEN = "\x1b[32m"
RESET = "\x1b[0m"


def _result(**overrides):
    base = {
        "run_id": "run0001",
        "original": "I has finish the task yesterday.",
        "output": "I finished the task yesterday.",
        "mode": "correction",
        "forced": False,
        "changes": [
            Change("equal", "I", "I"),
            Change("replace", "has finish", "finished"),
            Change("equal", "the task yesterday.", "the task yesterday."),
        ],
        "changed_ratio": 0.3333,
        "flags": [],
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "prompt_version": "1",
        "prompt_hash": "abcdef012345",
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_usd": 0.0002,
        "latency_ms": 250,
        "created_at": "2026-08-23T10:00:00Z",
        "error": None,
    }
    base.update(overrides)
    return Result(**base)


def test_plain_diff_uses_text_markers():
    diff = render_inline_diff(_result().changes, color=False)
    assert diff == "I [-has finish-]{+finished+} the task yesterday."


def test_coloured_diff_wraps_the_changed_words_only():
    diff = render_inline_diff(_result().changes, color=True)
    assert diff.startswith("I ")
    assert f"{RED}has finish{RESET}" in diff
    assert f"{GREEN}finished{RESET}" in diff
    assert "the task yesterday." in diff
    assert RED not in diff.split("finished")[-1]


def test_unchanged_text_renders_no_markers():
    changes = [Change("equal", "All good.", "All good.")]
    assert render_inline_diff(changes, color=False) == "All good."


def test_result_starts_with_the_clean_output():
    rendered = render_result(_result(), color=False)
    assert rendered.splitlines()[0] == "I finished the task yesterday."


def test_meta_line_carries_mode_ratio_model_latency_and_cost():
    rendered = render_result(_result(), color=False)
    assert "correction" in rendered
    assert "33%" in rendered
    assert "claude-haiku-4-5" in rendered
    assert "250ms" in rendered
    assert "$0.000200" in rendered


def test_unknown_cost_renders_as_a_dash_not_a_zero():
    rendered = render_result(_result(cost_usd=None), color=False)
    assert "$0.000000" not in rendered
    assert "cost n/a" in rendered


def test_forced_mode_is_marked():
    assert "forced" in render_result(_result(forced=True), color=False)


def test_flags_are_listed_on_their_own_line():
    rendered = render_result(_result(flags=["over_edit_suspected", "retried"]), color=False)
    assert "flags: over_edit_suspected, retried" in rendered


def test_no_flag_line_when_there_are_no_flags():
    assert "flags:" not in render_result(_result(), color=False)


def test_error_result_renders_the_error_and_no_diff():
    rendered = render_result(
        _result(output="", changes=[], changed_ratio=0.0, error="rate limited"), color=False
    )
    assert "error: rate limited" in rendered
    assert "[-" not in rendered
