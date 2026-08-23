import pytest

from slackchat import service as svc
from slackchat.cli import main as cli
from slackchat.config import Config
from slackchat.eval import runner
from slackchat.eval.assertions import Case
from slackchat.store import sqlite as store

# NOTE on the two fixed inputs below: the brief's literal CASES list used
# input="All good." / reply="All good, I think." for noop-x (changed_ratio
# 1.5) and input="I has finish the task yesterday." / reply="I finished the
# task yesterday." for fix-x (changed_ratio 0.3333). Both exceed the
# pipeline's internal Limits.max_changed_ratio=0.25 over-edit gate, which
# triggers `core/pipeline.py`'s single retry and consumes a second (unqueued)
# provider call per case -- with only one reply queued per case across these
# tests, FakeProvider runs out mid-suite. The inputs below were lengthened
# so every used reply's changed_ratio stays under 0.25, matching each test's
# intent (a real pass, and a real "output differs from input" failure)
# without ever crossing the pipeline's own internal retry gate. See the
# task-12 report for the exact diff_words() arithmetic.
CASES = [
    Case(
        id="noop-x",
        mode="correction",
        input="Everything looks fine to me today.",
        asserts={"unchanged": True},
    ),
    Case(
        id="fix-x",
        mode="correction",
        input="I has finish the task yesterday and reported back to the team.",
        asserts={"output_contains_any": ["I finished"], "max_changed_ratio": 0.4},
    ),
]

# Both cases untouched / correctly fixed: changed_ratio 0.0 and 0.1667.
_GREEN_REPLIES = [
    "Everything looks fine to me today.",
    "I finished the task yesterday and reported back to the team.",
]

# noop-x output differs from its input (fails the declared "unchanged"
# assertion) but changed_ratio stays 0.1667, under the pipeline's 0.25 gate,
# so it does not trigger a retry. fix-x is the same passing reply as above.
_FAILING_REPLIES = [
    "Everything looks fine to me now.",
    "I finished the task yesterday and reported back to the team.",
]


def _service(replies, isolated_paths, fake_provider, config=None):
    return svc.build_service(config or Config(), provider=fake_provider(replies))


def test_all_green_reports_full_pass_rate(isolated_paths, fake_provider):
    service = _service(_GREEN_REPLIES, isolated_paths, fake_provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert (summary.passed, summary.total) == (2, 2)
    text = "\n".join(lines)
    assert "2/2" in text


def test_a_failure_is_named_with_the_check_and_the_reason(isolated_paths, fake_provider):
    service = _service(_FAILING_REPLIES, isolated_paths, fake_provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert (summary.passed, summary.total) == (1, 2)
    text = "\n".join(lines)
    assert "noop-x" in text
    assert "unchanged" in text


def test_total_cost_is_printed_and_real(isolated_paths, fake_provider):
    service = _service(_GREEN_REPLIES, isolated_paths, fake_provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    # 2 runs x (100 input + 20 output) on Haiku pricing
    assert summary.cost_usd == pytest.approx(0.0004)
    assert "$0.0004" in "\n".join(lines)


def test_unknown_cost_runs_are_counted_not_treated_as_zero(isolated_paths, fake_provider):
    provider = fake_provider(_GREEN_REPLIES, model="local-llama")
    service = svc.build_service(Config(), provider=provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert summary.unknown_cost_runs == 2
    assert "2 run(s) with unknown pricing" in "\n".join(lines)


def test_runs_are_logged_as_eval_not_cli(isolated_paths, fake_provider):
    service = _service(_GREEN_REPLIES, isolated_paths, fake_provider)
    runner.run_suite(service, cases=CASES, out=lambda _l: None)
    conn = store.connect()
    assert {r["client"] for r in conn.execute("SELECT client FROM runs")} == {"eval"}


def test_every_check_outcome_is_persisted(isolated_paths, fake_provider):
    service = _service(_GREEN_REPLIES, isolated_paths, fake_provider)
    runner.run_suite(service, cases=CASES, out=lambda _l: None)
    conn = store.connect()
    rows = list(conn.execute("SELECT case_id, check_name, passed FROM eval_results"))
    assert {r["case_id"] for r in rows} == {"noop-x", "fix-x"}
    assert all(r["passed"] == 1 for r in rows)


def test_pass_rate_is_derivable_from_sql_afterwards(isolated_paths, fake_provider):
    service = _service(_FAILING_REPLIES, isolated_paths, fake_provider)
    runner.run_suite(service, cases=CASES, out=lambda _l: None)
    conn = store.connect()
    assert store.pass_rate(conn, "1") == (1, 2)


def test_compare_prints_both_versions(isolated_paths, sample_result, capsys):
    conn = store.connect()
    make_result = sample_result
    for version, run_id, passed in (("2", "a", True), ("3", "b", False)):
        store.insert_run(conn, make_result(run_id=run_id, prompt_version=version), client="eval")
        store.insert_eval_result(
            conn, run_id=run_id, case_id="c", check_name="unchanged", passed=passed
        )
    conn.close()
    lines = []
    runner.compare("2", "3", out=lines.append)
    text = "\n".join(lines)
    assert "version 2" in text and "1/1" in text
    assert "version 3" in text and "0/1" in text


def test_compare_warns_when_a_version_has_two_prompt_hashes(isolated_paths, sample_result):
    conn = store.connect()
    make_result = sample_result
    store.insert_run(conn, make_result(run_id="a", prompt_version="2", prompt_hash="aaa"), client="eval")
    store.insert_run(conn, make_result(run_id="b", prompt_version="2", prompt_hash="bbb"), client="eval")
    conn.close()
    lines = []
    runner.compare("2", "3", out=lines.append)
    text = "\n".join(lines)
    assert "warning" in text.lower()
    assert "prompt_version 2" in text


def test_eval_subcommand_runs_the_shipped_suite(isolated_paths, fake_provider, monkeypatch, capsys):
    provider = fake_provider(["x"] * 200)
    monkeypatch.setattr(
        cli, "build_service", lambda *a, **k: svc.build_service(Config(), provider=provider)
    )
    assert cli.main(["eval"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "pass rate" in out.lower()
    assert len(provider.calls) >= 20


def test_eval_compare_subcommand(isolated_paths, capsys):
    assert cli.main(["eval", "--compare", "1", "2"]) == cli.EXIT_OK
    assert "version 1" in capsys.readouterr().out
