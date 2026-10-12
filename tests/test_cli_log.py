import json

import pytest

from slackchat import service as svc
from slackchat.cli import main as cli
from slackchat.config import Config
from slackchat.store import sqlite as store


@pytest.fixture
def logged(isolated_paths, fake_provider, monkeypatch):
    def _run(texts, replies, *, client="cli"):
        provider = fake_provider(replies)
        service = svc.build_service(Config(), provider=provider)
        for text in texts:
            service.run(text, client=client)
        return store.connect()

    return _run


def test_a_run_is_logged_with_its_client(logged):
    conn = logged(
        ["I has finish the task we discussed yesterday."],
        ["I finished the task we discussed yesterday."],
    )
    row = conn.execute("SELECT client, mode, input, output FROM runs").fetchone()
    assert row["client"] == "cli"
    assert row["input"] == "I has finish the task we discussed yesterday."
    assert row["output"] == "I finished the task we discussed yesterday."


def test_changed_ratio_is_stored_so_trends_need_no_rediff(logged):
    conn = logged(
        ["I has finish the task we discussed yesterday."],
        ["I finished the task we discussed yesterday."],
    )
    assert conn.execute("SELECT changed_ratio FROM runs").fetchone()[0] == 0.25


def test_flags_are_stored_as_json(logged):
    conn = logged(["Deploy failed. Rollback done."], ["Deploy failed; rollback done."] * 2)
    flags = json.loads(conn.execute("SELECT flags FROM runs").fetchone()[0])
    assert "banned_char_introduced" in flags


def test_empty_input_writes_no_row(isolated_paths, fake_provider):
    from slackchat.core.types import EmptyInputError

    service = svc.build_service(Config(), provider=fake_provider([]))
    with pytest.raises(EmptyInputError):
        service.run("   ", client="cli")
    conn = store.connect()
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_a_failed_run_is_still_logged_with_its_error(isolated_paths, fake_provider):
    service = svc.build_service(Config(), provider=fake_provider([], error="rate limited"))
    service.run("I has finish", client="cli")
    conn = store.connect()
    assert conn.execute("SELECT error FROM runs").fetchone()[0] == "rate limited"


def test_three_runs_are_three_rows(logged):
    conn = logged(["a b c", "d e f", "g h i"], ["a b c", "d e f", "g h i"])
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3


def test_log_command_prints_the_most_recent_runs(logged, capsys):
    logged(
        [
            "I has finish the first task we discussed yesterday.",
            "I has finish the second task we discussed yesterday.",
        ],
        [
            "I finished the first task we discussed yesterday.",
            "I finished the second task we discussed yesterday.",
        ],
    )
    assert cli.main(["log", "--last", "1"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "second task" in out
    assert "first task" not in out


def test_log_command_filters_by_mode(logged, capsys):
    logged(
        ["I has finish the task we discussed yesterday.", "Tôi đã xong"],
        ["I finished the task we discussed yesterday.", "I am done"],
    )
    assert cli.main(["log", "--mode", "translation"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Tôi đã xong" in out
    assert "I has finish the task we discussed yesterday." not in out


def test_log_command_on_an_empty_database_says_so(isolated_paths, capsys):
    assert cli.main(["log"]) == cli.EXIT_OK
    assert "no runs" in capsys.readouterr().out.lower()
