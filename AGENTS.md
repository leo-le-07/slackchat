# AGENTS.md

`slackchat` — local English correction and Vietnamese-to-English translation.
One core service (`slackchat.core.pipeline.process`) behind a CLI and a
loopback HTTP daemon.

## Commands

Run everything through `uv`; do not activate the venv by hand.

- Install / refresh deps: `uv sync`
- All tests: `uv run pytest`
- One test file: `uv run pytest tests/test_detect.py -q`
- One test: `uv run pytest tests/test_detect.py::test_empty_and_whitespace_default_to_correction -q`
- Architecture boundaries: `uv run lint-imports`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Type check: `uv run mypy src`
- CLI: `uv run slackchat "text"`
- Eval golden set: `uv run slackchat eval`
- Compare prompt versions: `uv run slackchat eval --compare 5 6`
- Daemon: `uv run slackchat serve`
- CI runs: `uv sync --locked`, then `./scripts/check.sh`

Required before claiming done: `./scripts/check.sh` must exit 0. It runs, in
order, `ruff check`, `ruff format --check`, `mypy src`, `pytest`, and
`lint-imports`; it is the single source of truth for this sequence, so don't
restate the command list elsewhere — update the script instead.

## Architecture

`core/` and `providers/` are the inner layers. They must not import `cli/`,
`server/`, `store/`, `service`, or `config`. `core/` reaches the
provider only through the `Provider` Protocol in `providers/base.py`, never
`providers/anthropic.py`. `import-linter` enforces this; if a contract breaks,
the fix is the import, not the contract.

Logging is done by `service.py` after `process()` returns, never inside
`core/`.

## Conventions

- Python 3.14, stdlib first. `sqlite3`, `difflib`, `tomllib`, `argparse` are
  already enough for what they cover.
- `anthropic` 1.x runs on `httpx2`. Never `import httpx` in package code; it
  is a dev-only dependency for FastAPI's `TestClient`.
- Model id is `claude-haiku-4-5` with no date suffix. Haiku 4.5 rejects
  `output_config.effort`, and takes no `thinking` parameter.
- `ANTHROPIC_API_KEY` comes from the environment only. It never goes into a
  config file, a log row, or a test fixture.
- Tests never hit the network. Inject `FakeProvider` from `tests/conftest.py`.

## Config

Defaults live in `src/slackchat/config.py`; `config.example.toml` documents
them. The user's real config is `~/.config/slackchat/config.toml`. Tests must
never touch it — use the `isolated_paths` fixture, which points
`SLACKCHAT_CONFIG` and `SLACKCHAT_DB` at `tmp_path`.

Raising `max_changed_ratio` to stop an over-edit flag is the wrong fix. The
right fix is a tighter prompt and a bumped `version:`.

## The constraint that matters

Correction mode must not over-edit. A sentence that is already correct comes
back byte-for-byte. This is the project's primary guarantee. The `unchanged`
cases in `evals/correction.yaml` measure it; never loosen one to go green.
For any prompt edit, follow the `prompt-change` skill.
