import pytest

from slackchat.core.types import Limits, Result
from slackchat.eval.assertions import (
    KNOWN_ASSERTIONS,
    Case,
    check,
    load_cases,
)

LIMITS = Limits(max_changed_ratio=0.25, max_length_ratio=1.5, max_retries=1)


def _result(original, output, **overrides):
    from slackchat.core.diffing import diff_words

    changes, ratio = diff_words(original, output)
    base = {
        "run_id": "r1",
        "original": original,
        "output": output,
        "mode": "correction",
        "forced": False,
        "changes": changes,
        "changed_ratio": ratio,
        "flags": [],
        "provider": "fake",
        "model": "claude-haiku-4-5",
        "prompt_version": "1",
        "prompt_hash": "abcdef012345",
        "input_tokens": 10,
        "output_tokens": 10,
        "cost_usd": 0.0001,
        "latency_ms": 1,
        "created_at": "2026-08-23T10:00:00Z",
        "error": None,
    }
    base.update(overrides)
    return Result(**base)


def _names(outcomes):
    return {o.name for o in outcomes}


def _failed(outcomes):
    return {o.name for o in outcomes if not o.passed}


# --- universal checks -------------------------------------------------------


def test_the_four_universal_checks_run_without_being_declared():
    case = Case(id="c", mode="correction", input="all good", asserts={})
    outcomes = check(case, _result("all good", "all good"), LIMITS)
    assert _names(outcomes) == {
        "no_emoji",
        "no_banned_char_introduced",
        "non_empty",
        "length_ratio",
    }
    assert _failed(outcomes) == set()


def test_emoji_in_the_output_fails():
    case = Case(id="c", mode="correction", input="all good", asserts={})
    assert "no_emoji" in _failed(check(case, _result("all good", "all good 👍"), LIMITS))


def test_an_introduced_semicolon_fails():
    case = Case(id="c", mode="correction", input="Deploy failed. Rollback done.", asserts={})
    outcomes = check(
        case, _result("Deploy failed. Rollback done.", "Deploy failed; rollback done."), LIMITS
    )
    assert "no_banned_char_introduced" in _failed(outcomes)


def test_the_writers_own_em_dash_does_not_fail_a_correction_case():
    text = "It costs 30 dollars — more than expected."
    case = Case(id="c", mode="correction", input=text, asserts={})
    assert _failed(check(case, _result(text, text), LIMITS)) == set()


def test_an_em_dash_always_fails_a_translation_case():
    case = Case(id="c", mode="translation", input="Tôi xong rồi", asserts={})
    result = _result("Tôi xong rồi", "I am done — finally.", mode="translation")
    assert "no_banned_char_introduced" in _failed(check(case, result, LIMITS))


def test_empty_output_fails():
    case = Case(id="c", mode="correction", input="something", asserts={})
    assert "non_empty" in _failed(check(case, _result("something", ""), LIMITS))


def test_length_ratio_above_the_limit_fails():
    case = Case(id="c", mode="correction", input="one two", asserts={})
    result = _result("one two", "one two three four")  # ratio 2.0 > 1.5
    assert "length_ratio" in _failed(check(case, result, LIMITS))


def test_length_ratio_at_the_limit_passes():
    case = Case(id="c", mode="correction", input="one two", asserts={})
    result = _result("one two", "one two three")  # ratio 1.5
    assert "length_ratio" not in _failed(check(case, result, LIMITS))


# --- declared assertions ----------------------------------------------------


def test_unchanged_passes_on_identical_text():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert _failed(check(case, _result("All good.", "All good."), LIMITS)) == set()


def test_unchanged_ignores_trailing_whitespace_only():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert _failed(check(case, _result("All good.", "All good.  \n"), LIMITS)) == set()


def test_unchanged_is_byte_for_byte_otherwise():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert "unchanged" in _failed(check(case, _result("All good.", "All  good."), LIMITS))
    assert "unchanged" in _failed(check(case, _result("All good.", "all good."), LIMITS))


def test_output_contains_any_needs_one_match():
    case = Case(
        id="c",
        mode="correction",
        input="I has finish",
        asserts={"output_contains_any": ["I finished", "I have finished"]},
    )
    assert _failed(check(case, _result("I has finish", "I have finished"), LIMITS)) == set()
    assert "output_contains_any" in _failed(
        check(case, _result("I has finish", "I did complete it"), LIMITS)
    )


def test_output_excludes_fails_on_any_hit():
    # 4-word input, kept >= the reply's word count: a 1-word "x" input would
    # trip the unrelated length_ratio universal check on any short reply
    # (word_count("Please review")/word_count("x") = 2.0 > the 1.5 limit),
    # which is not what this test is about.
    case = Case(
        id="c",
        mode="correction",
        input="Please take a look",
        asserts={"output_excludes": ["kindly"]},
    )
    assert "output_excludes" in _failed(
        check(case, _result("Please take a look", "Kindly review this"), LIMITS)
    )
    assert (
        _failed(check(case, _result("Please take a look", "Please review this"), LIMITS)) == set()
    )


def test_max_changed_ratio_overrides_the_default_for_one_case():
    case = Case(
        id="c",
        mode="correction",
        input="I has finish the task yesterday.",
        asserts={"max_changed_ratio": 0.4},
    )
    result = _result("I has finish the task yesterday.", "I finished the task yesterday.")
    assert _failed(check(case, result, LIMITS)) == set()  # 0.3333 <= 0.4


def test_max_words_counts_output_words():
    case = Case(id="c", mode="correction", input="Any concerns?", asserts={"max_words": 3})
    assert _failed(check(case, _result("Any concerns?", "Any concerns?"), LIMITS)) == set()
    assert "max_words" in _failed(
        check(case, _result("Any concerns?", "Do you have any concerns at all?"), LIMITS)
    )


def test_an_unknown_assertion_key_is_an_error():
    case = Case(id="c", mode="correction", input="x", asserts={"vibes": "good"})
    with pytest.raises(ValueError, match="vibes"):
        check(case, _result("x", "x"), LIMITS)


def test_known_assertions_is_exactly_the_documented_five():
    assert (
        frozenset(
            {
                "unchanged",
                "output_contains_any",
                "output_excludes",
                "max_changed_ratio",
                "max_words",
            }
        )
        == KNOWN_ASSERTIONS
    )


# --- loading ----------------------------------------------------------------


def test_the_shipped_cases_load_and_every_key_is_known():
    cases = load_cases()
    assert len(cases) >= 20
    assert {c.mode for c in cases} == {"correction", "translation"}
    for case in cases:
        assert set(case.asserts) <= KNOWN_ASSERTIONS, case.id


def test_case_ids_are_unique():
    ids = [c.id for c in load_cases()]
    assert len(ids) == len(set(ids))


def test_at_least_ten_unchanged_cases_exist():
    unchanged = [c for c in load_cases() if c.asserts.get("unchanged")]
    assert len(unchanged) >= 10


def test_load_cases_from_a_custom_directory(tmp_path):
    (tmp_path / "x.yaml").write_text(
        '- id: a\n  mode: correction\n  input: "hi"\n  assert: { unchanged: true }\n',
        encoding="utf-8",
    )
    cases = load_cases(tmp_path)
    assert [c.id for c in cases] == ["a"]


def test_a_duplicate_id_across_files_is_an_error(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(
            '- id: dup\n  mode: correction\n  input: "hi"\n  assert: {}\n', encoding="utf-8"
        )
    with pytest.raises(ValueError, match="dup"):
        load_cases(tmp_path)
