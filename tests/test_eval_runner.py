from slackchat import service as svc
from slackchat.cli import main as cli
from slackchat.config import Config
from slackchat.core import prompts
from slackchat.eval.cases import Case
from slackchat.eval.runner import compare, run_suite

KEEP = Case(id="keep", group="unchanged", input="Is that okay?")
FIX = Case(
    id="fix", group="needs_fix", input="Is it okey?", include=("okay",), reference="Is it okay?"
)


def run(replies, cases, version=None, monkeypatch=None, fake_provider=None):
    if version is not None:
        real = prompts.load_prompt

        def fake_load(mode, prompts_dir=None):
            p = real(mode, prompts_dir)
            return prompts.Prompt(mode=p.mode, version=version, text=p.text, hash=p.hash)

        monkeypatch.setattr("slackchat.core.pipeline.load_prompt", fake_load)
        monkeypatch.setattr("slackchat.eval.runner.load_prompt", fake_load)
    service = svc.build_service(Config(), provider=fake_provider(replies))
    lines = []
    code = run_suite(service, cases, out=lines.append)
    return code, "\n".join(lines)


def test_suite_passes_when_output_is_right(isolated_paths, fake_provider):
    code, text = run(["Is that okay?", "Is it okay?"], [KEEP, FIX], fake_provider=fake_provider)
    assert code == 0
    assert "unchanged: 1/1" in text and "needs_fix: 1/1" in text


def test_changed_unchanged_case_fails_and_returns_1(isolated_paths, fake_provider):
    code, text = run(["Is that fine?"], [KEEP], fake_provider=fake_provider)
    assert code == 1
    assert "FAIL keep" in text


def test_reference_mismatch_is_soft(isolated_paths, fake_provider):
    code, text = run(["Is it okay!"], [FIX], fake_provider=fake_provider)
    assert code == 0
    assert "differs from reference" in text


def test_compare_flags_a_regression(isolated_paths, fake_provider, monkeypatch):
    run(["Is that okay?"], [KEEP], "1", monkeypatch, fake_provider)
    run(["Is that fine?"], [KEEP], "2", monkeypatch, fake_provider)
    lines = []
    code = compare("1", "2", [KEEP], default_max_ratio=0.35, out=lines.append)
    text = "\n".join(lines)
    assert code == 1
    assert "▼ keep" in text
    assert "[-okay?-] {+fine?+}" in text


def test_same_version_new_hash_warns(isolated_paths, fake_provider, monkeypatch):
    run(["Is that okay?"], [KEEP], fake_provider=fake_provider)
    monkeypatch.setattr(
        "slackchat.eval.runner.load_prompt",
        lambda mode: prompts.Prompt(mode=mode, version="5", text="x", hash="deadbeef0000"),
    )
    service = svc.build_service(Config(), provider=fake_provider(["Is that okay?"]))
    lines = []
    run_suite(service, [KEEP], out=lines.append)
    assert "bump version:" in lines[0]


def test_compare_missing_version_is_clear(isolated_paths, fake_provider, capsys):
    lines = []
    assert compare("8", "9", [KEEP], default_max_ratio=0.35, out=lines.append) == 2
    assert "no eval runs for prompt version 8" in lines[0]


def test_cli_without_case_file_is_a_usage_error(isolated_paths, capsys):
    assert cli.main(["eval"]) == cli.EXIT_USAGE
    assert "not found" in capsys.readouterr().err
