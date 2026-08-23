import pytest

from slackchat.core.validate import (
    BANNED_CHARS,
    FLAG_BANNED_CHAR,
    FLAG_EMPTY_OUTPUT,
    FLAG_OVER_EDIT,
    banned_chars_introduced,
    find_violations,
    mechanical_replace,
    retry_suffix,
    sanitize,
)


# --- sanitize ---------------------------------------------------------------

def test_sanitize_removes_emoji_and_tidies_the_gap():
    assert sanitize("Thanks! 🙏 Looks good ✅") == "Thanks! Looks good"


def test_sanitize_removes_emoji_with_variation_selector():
    assert sanitize("Second line ✈️  here") == "Second line here"


def test_sanitize_preserves_newlines():
    assert sanitize("one 🎉\ntwo") == "one\ntwo"


def test_sanitize_leaves_ordinary_punctuation_alone():
    text = "It costs 30° and 50% — fine; ok…"
    assert sanitize(text) == text


def test_sanitize_strips_leading_and_trailing_whitespace():
    assert sanitize("  hello  \n") == "hello"


def test_sanitize_never_touches_semicolon_or_em_dash():
    # Mechanical substitution of these guesses; sanitize must not guess.
    assert ";" in sanitize("a; b")
    assert "—" in sanitize("a — b")


# --- banned characters ------------------------------------------------------

def test_banned_chars_are_ordered_and_deduped():
    assert BANNED_CHARS == (";", "—")


def test_correction_keeps_the_writers_own_em_dash():
    assert banned_chars_introduced("I shipped it — finally.", "I shipped it — finally.", "correction") == []


def test_correction_flags_an_em_dash_the_model_added():
    assert banned_chars_introduced("I shipped it finally.", "I shipped it — finally.", "correction") == ["—"]


def test_correction_flags_a_semicolon_the_model_added():
    assert banned_chars_introduced("Deploy failed. Rollback done.", "Deploy failed; rollback done.", "correction") == [";"]


def test_translation_bans_unconditionally_even_if_the_source_had_one():
    assert banned_chars_introduced("Tôi xong; anh xem nhé", "I am done; please review", "translation") == [";"]


# --- find_violations --------------------------------------------------------

def test_clean_correction_has_no_violations():
    assert find_violations(
        original="The deployment failed.",
        output="The deployment failed.",
        mode="correction",
        changed_ratio=0.0,
        max_changed_ratio=0.25,
    ) == []


def test_over_edit_above_the_limit_is_flagged():
    violations = find_violations(
        original="The deployment failed because the config was missing.",
        output="Unfortunately, the deployment was unsuccessful due to a missing configuration.",
        mode="correction",
        changed_ratio=0.75,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_OVER_EDIT]
    assert "byte-for-byte" in violations[0].instruction


def test_over_edit_is_not_checked_in_translation_mode():
    assert find_violations(
        original="Tôi đã hoàn thành task hôm qua.",
        output="I finished the task yesterday.",
        mode="translation",
        changed_ratio=3.0,
        max_changed_ratio=0.25,
    ) == []


def test_ratio_exactly_at_the_limit_passes():
    assert find_violations(
        original="a b c d",
        output="a b c e",
        mode="correction",
        changed_ratio=0.25,
        max_changed_ratio=0.25,
    ) == []


def test_empty_output_short_circuits_every_other_check():
    violations = find_violations(
        original="something",
        output="   ",
        mode="correction",
        changed_ratio=1.0,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_EMPTY_OUTPUT]


def test_multiple_banned_chars_share_one_flag_but_give_two_instructions():
    violations = find_violations(
        original="Deploy failed. Rollback done. All good.",
        output="Deploy failed; rollback done — all good.",
        mode="correction",
        changed_ratio=0.1,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_BANNED_CHAR, FLAG_BANNED_CHAR]
    assert "semicolon" in violations[0].instruction
    assert "em dash" in violations[1].instruction


# --- retry suffix -----------------------------------------------------------

def test_retry_suffix_lists_each_instruction():
    violations = find_violations(
        original="Deploy failed. Rollback done.",
        output="Deploy failed; rollback done.",
        mode="correction",
        changed_ratio=0.1,
        max_changed_ratio=0.25,
    )
    suffix = retry_suffix(violations)
    assert suffix.startswith("\n\n")
    assert "rejected" in suffix
    assert suffix.count("\n- ") == 1


def test_retry_suffix_is_empty_without_violations():
    assert retry_suffix([]) == ""


# --- mechanical fallback ----------------------------------------------------

@pytest.mark.parametrize(
    "given,expected",
    [
        ("We shipped it — the tests passed; all good.", "We shipped it, the tests passed, all good."),
        ("Deploy failed; rollback done.", "Deploy failed, rollback done."),
        ("It works—mostly.", "It works, mostly."),
        ("a — ; b", "a, b"),
        ("Steps:\n- one;\n- two — three", "Steps:\n- one,\n- two, three"),
        ("nothing to do here", "nothing to do here"),
    ],
)
def test_mechanical_replace(given, expected):
    assert mechanical_replace(given) == expected
