import pytest

from slackchat.cli import repl
from slackchat.config import Config


class Reader:
    """Stands in for input(). Raises EOFError when the script runs out."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


@pytest.fixture
def session(isolated_paths, fake_provider):
    def _session(lines, replies, *, copy_fn=None):
        from slackchat import service as svc

        provider = fake_provider(replies)
        service = svc.build_service(Config(), provider=provider)
        reader = Reader(lines)
        written = []
        code = repl.run_session(
            service,
            read_line=reader,
            write=written.append,
            color=False,
            copy_fn=copy_fn or (lambda _text: False),
        )
        return code, provider, reader, "".join(written)

    return _session


def test_banner_is_printed_once_at_the_start(session):
    _, _, _, out = session([], [])
    assert out.count("Ctrl+D or /exit to quit") == 1


def test_a_single_line_turn_is_submitted_on_the_blank_line(session):
    code, provider, reader, out = session(
        ["I has finish the task we discussed yesterday.", ""],
        ["I finished the task we discussed yesterday."],
    )
    assert code == 0
    assert len(provider.calls) == 1
    assert provider.calls[0]["user"] == "I has finish the task we discussed yesterday."
    assert "I finished the task we discussed yesterday." in out


def test_prompts_switch_to_the_continuation_form_after_the_first_line(session):
    _, _, reader, _ = session(["one", "two", ""], ["one\ntwo"])
    assert reader.prompts[:3] == [repl.PROMPT, repl.CONTINUATION, repl.CONTINUATION]


def test_a_multi_line_paste_is_one_input_joined_by_newlines(session):
    _, provider, _, _ = session(
        ["line one", "line two", "line three", ""],
        ["line one\nline two\nline three"],
    )
    assert len(provider.calls) == 1
    assert provider.calls[0]["user"] == "line one\nline two\nline three"


def test_two_turns_are_two_runs(session):
    _, provider, _, _ = session(["first", "", "second", ""], ["first", "second"])
    assert [c["user"] for c in provider.calls] == ["first", "second"]


def test_blank_line_with_an_empty_buffer_is_ignored_silently(session):
    code, provider, reader, out = session(
        ["", "", "real input", ""], ["real input"]
    )
    assert len(provider.calls) == 1
    assert "empty" not in out.lower()
    assert "error" not in out.lower()
    # prompt returns to the primary form each time
    assert reader.prompts[:3] == [repl.PROMPT, repl.PROMPT, repl.PROMPT]


@pytest.mark.parametrize("word", ["/exit", "/quit"])
def test_exit_words_leave_immediately(session, word):
    code, provider, _, _ = session([word, "never reached", ""], ["out"])
    assert code == 0
    assert provider.calls == []


def test_exit_word_mid_input_discards_the_buffer_and_leaves(session):
    code, provider, _, _ = session(["half a thought", "/exit"], ["out"])
    assert code == 0
    assert provider.calls == []


def test_exit_word_is_matched_after_stripping_whitespace(session):
    code, provider, _, _ = session(["  /exit  "], ["out"])
    assert code == 0
    assert provider.calls == []


def test_eof_leaves_immediately(session):
    code, provider, _, _ = session([], ["out"])
    assert code == 0
    assert provider.calls == []


def test_ctrl_c_leaves_immediately(isolated_paths, fake_provider):
    from slackchat import service as svc

    def reader(_prompt):
        raise KeyboardInterrupt

    service = svc.build_service(Config(), provider=fake_provider([]))
    written = []
    assert (
        repl.run_session(
            service, read_line=reader, write=written.append, color=False, copy_fn=lambda _t: False
        )
        == 0
    )


def test_each_turn_copies_when_the_copy_function_succeeds(session):
    copied = []
    _, _, _, out = session(
        ["a b c", "", "d e f", ""], ["a b c", "d e f"], copy_fn=lambda t: copied.append(t) or True
    )
    assert copied == ["a b c", "d e f"]
    assert out.count("(copied to clipboard)") == 2


def test_a_provider_error_is_shown_and_the_session_continues(isolated_paths, fake_provider):
    from slackchat import service as svc

    provider = fake_provider([], error="rate limited")
    service = svc.build_service(Config(), provider=provider)
    reader = Reader(["something", "", "another", ""])
    written = []
    code = repl.run_session(
        service, read_line=reader, write=written.append, color=False, copy_fn=lambda _t: False
    )
    out = "".join(written)
    assert code == 0
    assert out.count("rate limited") == 2  # the session did not abort on the first
