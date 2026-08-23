import pytest

from slackchat.eval import review
from slackchat.store import sqlite as store


class Reader:
    def __init__(self, answers):
        self._answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)


@pytest.fixture
def seeded(isolated_paths, sample_result):
    def _seed(specs):
        conn = store.connect()
        for run_id, mode, client in specs:
            store.insert_run(
                conn, sample_result(run_id=run_id, mode=mode), client=client
            )
        return conn

    return _seed


def test_only_eval_runs_are_offered(seeded):
    conn = seeded([("a", "correction", "eval"), ("b", "correction", "cli")])
    assert [r["run_id"] for r in review.unreviewed_runs(conn, limit=10)] == ["a"]


def test_already_reviewed_runs_are_skipped(seeded):
    conn = seeded([("a", "correction", "eval"), ("b", "correction", "eval")])
    store.insert_review(
        conn,
        run_id="a",
        dimension="Minimality",
        score=2,
        reviewer="human",
        note=None,
        created_at="2026-08-23T10:00:00Z",
    )
    assert [r["run_id"] for r in review.unreviewed_runs(conn, limit=10)] == ["b"]


def test_a_run_reviewed_by_a_judge_is_still_offered_to_a_human(seeded):
    conn = seeded([("a", "correction", "eval")])
    store.insert_review(
        conn,
        run_id="a",
        dimension="Minimality",
        score=2,
        reviewer="claude-haiku-4-5",
        note=None,
        created_at="2026-08-23T10:00:00Z",
    )
    assert [r["run_id"] for r in review.unreviewed_runs(conn, limit=10, reviewer="human")] == ["a"]


def test_limit_is_respected(seeded):
    conn = seeded([(f"r{i}", "correction", "eval") for i in range(5)])
    assert len(review.unreviewed_runs(conn, limit=2)) == 2


def test_a_correction_run_asks_for_three_scores_and_a_note(seeded):
    conn = seeded([("a", "correction", "eval")])
    reader = Reader(["2", "2", "1", "kept the hedge"])
    written = []
    scored = review.review_session(
        conn,
        limit=1,
        read_line=reader,
        write=written.append,
        clock=lambda: "2026-08-23T10:00:00Z",
    )
    assert scored == 1
    rows = list(conn.execute("SELECT dimension, score, reviewer, note FROM reviews ORDER BY dimension"))
    assert [(r["dimension"], r["score"]) for r in rows] == [
        ("Correctness", 2),
        ("Minimality", 2),
        ("Voice preservation", 1),
    ]
    assert {r["reviewer"] for r in rows} == {"human"}
    assert {r["note"] for r in rows} == {"kept the hedge"}


def test_a_translation_run_asks_for_four_scores(seeded):
    conn = seeded([("a", "translation", "eval")])
    reader = Reader(["2", "2", "2", "2", ""])
    review.review_session(
        conn, limit=1, read_line=reader, write=lambda _l: None, clock=lambda: "t"
    )
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 4


def test_the_input_and_output_are_shown_before_scoring(seeded):
    conn = seeded([("a", "correction", "eval")])
    written = []
    review.review_session(
        conn,
        limit=1,
        read_line=Reader(["2", "2", "2", ""]),
        write=written.append,
        clock=lambda: "t",
    )
    text = "\n".join(written)
    assert "I has finish" in text
    assert "I finished" in text


def test_an_invalid_score_reprompts_without_writing(seeded):
    conn = seeded([("a", "correction", "eval")])
    reader = Reader(["5", "x", "2", "2", "2", ""])
    review.review_session(
        conn, limit=1, read_line=reader, write=lambda _l: None, clock=lambda: "t"
    )
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 3
    assert len([p for p in reader.prompts if "Minimality" in p]) == 3


def test_eof_mid_run_stops_cleanly_without_a_partial_row(seeded):
    conn = seeded([("a", "correction", "eval")])
    scored = review.review_session(
        conn, limit=1, read_line=Reader(["2"]), write=lambda _l: None, clock=lambda: "t"
    )
    assert scored == 0
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0


def test_nothing_to_review_is_reported(seeded):
    conn = seeded([])
    written = []
    assert (
        review.review_session(
            conn, limit=5, read_line=Reader([]), write=written.append, clock=lambda: "t"
        )
        == 0
    )
    assert "nothing to review" in "\n".join(written).lower()


def test_review_subcommand_is_wired(isolated_paths, capsys):
    from slackchat.cli import main as cli

    assert cli.main(["eval", "--review"]) == cli.EXIT_OK
    assert "nothing to review" in capsys.readouterr().out.lower()
