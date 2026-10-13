import pytest

from slackchat.eval.cases import Case, check, load_cases


def run(case, output, *, ratio=0.1, flags=(), error=None):
    return check(
        case,
        output=output,
        changed_ratio=ratio,
        flags=list(flags),
        error=error,
        default_max_ratio=0.35,
    )


KEEP = Case(id="k", group="unchanged", input="Is that okay?")
FIX = Case(
    id="f",
    group="needs_fix",
    input="Is it okey?",
    include=("okay",),
    exclude=("okey",),
)


def test_unchanged_passes_on_identical_output_and_ignores_trailing_whitespace():
    assert run(KEEP, "Is that okay?\n") == []


def test_unchanged_fails_on_any_changed_byte():
    assert run(KEEP, "Is that okay.") == ["output differs from input"]


def test_needs_fix_include_and_exclude():
    assert run(FIX, "Is it okay?") == []
    assert run(FIX, "Is it fine?") == ["missing 'okay'"]
    assert "still has 'okey'" in run(FIX, "Is it okey, okay?")


def test_blocking_flag_fails_but_retried_does_not():
    assert run(FIX, "Is it okay?", flags=["retried"]) == []
    assert run(FIX, "Is it okay?", flags=["over_edit_suspected"]) == ["flag: over_edit_suspected"]


def test_error_short_circuits():
    assert run(FIX, "", error="boom") == ["error: boom"]


def test_line_count_must_match():
    two = Case(id="t", group="needs_fix", input="a\nb")
    assert run(two, "a b") == ["line count changed"]


def test_ratio_uses_case_limit_then_default():
    assert run(FIX, "Is it okay?", ratio=0.5) == ["changed_ratio 0.50 > 0.35"]
    loose = Case(id="l", group="needs_fix", input="Is it okey?", max_changed_ratio=0.6)
    assert run(loose, "Is it okay?", ratio=0.5) == []


def write(tmp_path, text):
    path = tmp_path / "c.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_keeps_multiline_input_without_trailing_newline(tmp_path):
    path = write(tmp_path, "- id: a\n  group: unchanged\n  input: |-\n    one\n    two\n")
    assert load_cases(path)[0].input == "one\ntwo"


@pytest.mark.parametrize(
    "body, message",
    [
        (
            "- {id: a, group: unchanged, input: x}\n- {id: a, group: unchanged, input: y}",
            "duplicate",
        ),
        ("- {id: a, group: nope, input: x}", "unknown group"),
        ("- {id: a, group: unchanged, input: x, color: red}", "unknown key"),
        ("- {id: a, group: unchanged, input: x, include: [x]}", "takes no other fields"),
        ("- {id: a, group: needs_fix, input: '  '}", "input is empty"),
        ("- {id: a, group: needs_fix, input: 'Tôi đã xong việc rồi'}", "translation mode"),
    ],
)
def test_load_rejects_bad_cases(tmp_path, body, message):
    with pytest.raises(ValueError, match=message):
        load_cases(write(tmp_path, body))


def test_load_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_cases(tmp_path / "nope.yaml")
