import subprocess

import pytest

from slackchat.cli import clipboard
from slackchat.cli import main as cli
from slackchat.config import CliConfig, Config


def test_copy_shells_out_to_pbcopy(monkeypatch):
    seen = {}

    def fake_run(cmd, *, input, check, capture_output):
        seen["cmd"] = cmd
        seen["input"] = input
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    assert clipboard.copy("hello") is True
    assert seen["cmd"] == ["pbcopy"]
    assert seen["input"] == b"hello"


def test_copy_returns_false_when_pbcopy_is_missing(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("pbcopy")

    monkeypatch.setattr(clipboard.subprocess, "run", boom)
    assert clipboard.copy("hello") is False


def test_copy_returns_false_when_pbcopy_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["pbcopy"])

    monkeypatch.setattr(clipboard.subprocess, "run", boom)
    assert clipboard.copy("hello") is False


@pytest.fixture
def wired(monkeypatch, isolated_paths, fake_provider):
    def _wire(reply, *, auto_copy=True, stdout_tty=True):
        from slackchat import service as svc

        provider = fake_provider(reply)
        config = Config(cli=CliConfig(auto_copy=auto_copy))
        monkeypatch.setattr(
            cli, "build_service", lambda *a, **k: svc.build_service(config, provider=provider)
        )
        monkeypatch.setattr(cli, "_stdout_is_tty", lambda: stdout_tty)
        copied = []
        monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: copied.append(text) or True)
        return copied

    return _wire


def test_tty_and_auto_copy_on_copies_the_clean_output(wired, capsys):
    copied = wired("I finished the task we discussed yesterday.")
    cli.main(["I has finish the task we discussed yesterday."])
    assert copied == ["I finished the task we discussed yesterday."]
    assert "(copied to clipboard)" in capsys.readouterr().out


def test_the_copied_text_never_contains_escape_codes(wired, capsys):
    copied = wired("I finished the task we discussed yesterday.")
    cli.main(["I has finish the task we discussed yesterday."])
    assert "\x1b" not in copied[0]


def test_piped_stdout_copies_nothing_and_says_nothing(wired, capsys):
    copied = wired("I finished the task we discussed yesterday.", stdout_tty=False)
    cli.main(["I has finish the task we discussed yesterday."])
    assert copied == []
    assert "copied" not in capsys.readouterr().out


def test_auto_copy_off_copies_nothing(wired, capsys):
    copied = wired("I finished the task we discussed yesterday.", auto_copy=False)
    cli.main(["I has finish the task we discussed yesterday."])
    assert copied == []
    assert "copied" not in capsys.readouterr().out


def test_raw_on_a_tty_still_copies(wired, capsys):
    copied = wired("I finished the task we discussed yesterday.")
    cli.main(["--raw", "I has finish the task we discussed yesterday."])
    assert copied == ["I finished the task we discussed yesterday."]


def test_an_errored_result_is_not_copied(wired, capsys, monkeypatch, isolated_paths, fake_provider):
    from slackchat import service as svc

    provider = fake_provider([], error="rate limited")
    monkeypatch.setattr(
        cli, "build_service", lambda *a, **k: svc.build_service(Config(), provider=provider)
    )
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
    copied = []
    monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: copied.append(text) or True)
    cli.main(["I has finish"])
    assert copied == []
