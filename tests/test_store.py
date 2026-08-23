import json
import sqlite3

import pytest

# pytest's default import mode puts tests/ on sys.path, so the conftest helper
# is importable by name. Do not redefine the builder here — one definition.
from conftest import make_result as _result
from slackchat.store import sqlite as store


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "nested" / "runs.db")
    yield connection
    connection.close()


def test_connect_creates_the_parent_directory_and_the_file(tmp_path):
    path = tmp_path / "a" / "b" / "runs.db"
    store.connect(path).close()
    assert path.exists()


def test_wal_is_enabled(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_review(
            conn,
            run_id="nope",
            dimension="Minimality",
            score=2,
            reviewer="human",
            note=None,
            created_at="2026-08-23T10:00:00Z",
        )


def test_insert_run_round_trips_every_column(conn):
    store.insert_run(conn, _result(), client="cli")
    row = conn.execute("SELECT * FROM runs").fetchone()
    assert row["run_id"] == "run0001"
    assert row["client"] == "cli"
    assert row["mode"] == "correction"
    assert row["forced"] == 0
    assert row["input"] == "I has finish"
    assert row["output"] == "I finished"
    assert row["changed_ratio"] == 0.5
    assert json.loads(row["flags"]) == ["retried"]
    assert row["cost_usd"] == 0.0002
    assert row["error"] is None


def test_forced_is_stored_as_one(conn):
    store.insert_run(conn, _result(forced=True), client="cli")
    assert conn.execute("SELECT forced FROM runs").fetchone()[0] == 1


def test_unknown_cost_is_stored_as_null_not_zero(conn):
    store.insert_run(conn, _result(cost_usd=None), client="cli")
    assert conn.execute("SELECT cost_usd FROM runs").fetchone()[0] is None


def test_empty_flags_store_as_an_empty_json_array(conn):
    store.insert_run(conn, _result(flags=[]), client="cli")
    assert json.loads(conn.execute("SELECT flags FROM runs").fetchone()[0]) == []


def test_recent_runs_is_newest_first_and_respects_the_limit(conn):
    for i, stamp in enumerate(["2026-08-23T10:00:00Z", "2026-08-23T11:00:00Z", "2026-08-23T12:00:00Z"]):
        store.insert_run(conn, _result(run_id=f"r{i}", created_at=stamp), client="cli")
    rows = store.recent_runs(conn, limit=2)
    assert [r["run_id"] for r in rows] == ["r2", "r1"]


def test_recent_runs_filters_by_mode(conn):
    store.insert_run(conn, _result(run_id="a", mode="correction"), client="cli")
    store.insert_run(conn, _result(run_id="b", mode="translation"), client="cli")
    rows = store.recent_runs(conn, mode="translation")
    assert [r["run_id"] for r in rows] == ["b"]


def test_reviews_are_keyed_by_reviewer_so_a_judge_can_be_added_later(conn):
    store.insert_run(conn, _result(), client="eval")
    for reviewer in ("human", "claude-haiku-4-5"):
        store.insert_review(
            conn,
            run_id="run0001",
            dimension="Minimality",
            score=2,
            reviewer=reviewer,
            note=None,
            created_at="2026-08-23T10:00:00Z",
        )
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 2


def test_a_score_outside_zero_one_two_is_rejected(conn):
    store.insert_run(conn, _result(), client="eval")
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_review(
            conn,
            run_id="run0001",
            dimension="Minimality",
            score=3,
            reviewer="human",
            note=None,
            created_at="2026-08-23T10:00:00Z",
        )


def test_pass_rate_counts_runs_not_checks(conn):
    store.insert_run(conn, _result(run_id="p1", prompt_version="1"), client="eval")
    store.insert_run(conn, _result(run_id="p2", prompt_version="1"), client="eval")
    store.insert_eval_result(conn, run_id="p1", case_id="noop-001", check_name="unchanged", passed=True)
    store.insert_eval_result(conn, run_id="p1", case_id="noop-001", check_name="no_emoji", passed=True)
    store.insert_eval_result(conn, run_id="p2", case_id="fix-001", check_name="unchanged", passed=False)
    passed, total = store.pass_rate(conn, "1")
    assert (passed, total) == (1, 2)


def test_prompt_hash_conflicts_reports_a_version_with_two_hashes(conn):
    store.insert_run(conn, _result(run_id="x", prompt_version="1", prompt_hash="aaa"), client="eval")
    store.insert_run(conn, _result(run_id="y", prompt_version="1", prompt_hash="bbb"), client="eval")
    store.insert_run(conn, _result(run_id="z", prompt_version="2", prompt_hash="ccc"), client="eval")
    assert store.prompt_hash_conflicts(conn) == [("1", 2)]
