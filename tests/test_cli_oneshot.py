import os

import pytest

from slackchat.cli import main as cli
from slackchat.config import Config


@pytest.fixture
def wire(monkeypatch, isolated_paths, fake_provider):
    """Replace build_service with one backed by FakeProvider."""

    def _wire(replies, *, config=None, error=None):
        from slackchat import service as svc

        provider = fake_provider(replies, error=error)
        real = svc.build_service

        def fake_build(cfg=None, provider_override=None):
            return real(config or Config(), provider=provider)

        monkeypatch.setattr(cli, "build_service", fake_build)
        return provider

    return _wire


def test_one_shot_prints_output_and_diff(wire, capsys):
    wire("I finished the task we discussed yesterday.")
    code = cli.main(["I has finish the task we discussed yesterday."])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.splitlines()[0] == "I finished the task we discussed yesterday."
    assert "[-has finish-]" in out
    assert "correction" in out


def test_raw_prints_only_the_output_text(wire, capsys):
    wire("I finished the task we discussed yesterday.")
    code = cli.main(["--raw", "I has finish the task we discussed yesterday."])
    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "I finished the task we discussed yesterday.\n"


def test_mode_flag_forces_the_mode(wire, capsys):
    provider = wire("I am done.")
    code = cli.main(["--mode", "translation", "I has finish"])
    assert code == cli.EXIT_OK
    assert "translation (forced)" in capsys.readouterr().out
    assert len(provider.calls) == 1


def test_bad_mode_value_is_a_usage_error(wire, capsys):
    wire([])
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--mode", "rewrite", "text"])
    assert excinfo.value.code == cli.EXIT_USAGE


def test_vietnamese_auto_routes_to_translation(wire, capsys):
    wire("I finished the task yesterday.")
    cli.main(["Tôi đã hoàn thành task hôm qua."])
    out = capsys.readouterr().out
    assert "translation" in out
    assert "(forced)" not in out


def test_detect_subcommand_prints_the_mode_and_calls_nothing(wire, capsys):
    provider = wire([])
    assert cli.main(["detect", "Tôi đã xong"]) == cli.EXIT_OK
    assert capsys.readouterr().out == "translation\n"
    assert provider.calls == []


def test_detect_subcommand_on_english(wire, capsys):
    wire([])
    assert cli.main(["detect", "The build is green"]) == cli.EXIT_OK
    assert capsys.readouterr().out == "correction\n"


def test_empty_argument_exits_nonzero_without_calling_the_api(wire, capsys):
    provider = wire([])
    assert cli.main(["   "]) == cli.EXIT_EMPTY_INPUT
    assert provider.calls == []
    assert "empty" in capsys.readouterr().err.lower()


def test_piped_stdin_is_processed_as_one_batch(wire, capsys, monkeypatch):
    provider = wire("line one\nline two")
    monkeypatch.setattr(cli, "_read_stdin", lambda: "line one\nline two\n")
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: False)
    assert cli.main([]) == cli.EXIT_OK
    assert len(provider.calls) == 1
    assert provider.calls[0]["user"] == "line one\nline two"


def test_provider_error_exits_three_and_reports_on_stderr(wire, capsys):
    wire([], error="rate limited")
    assert cli.main(["I has finish"]) == cli.EXIT_PROVIDER_ERROR
    captured = capsys.readouterr()
    assert "rate limited" in captured.err


def test_a_quoted_input_that_starts_with_a_subcommand_word_is_still_text(wire, capsys):
    # "detect the bug ..." is one argv entry, so it is text, not the subcommand.
    wire("Detect the bug in staging before it reaches production.")
    assert cli.main(["detect the bug in staging before it reaches production"]) == cli.EXIT_OK


def test_a_dotenv_file_in_the_working_directory_is_loaded(
    wire, capsys, monkeypatch, isolated_paths
):
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    (isolated_paths / ".env").write_text("SLACKCHAT_TEST_KEY=hello\n", encoding="utf-8")
    wire("I finished the task we discussed yesterday.")
    cli.main(["I has finish the task we discussed yesterday."])
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello"
