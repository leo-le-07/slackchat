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
- CLI: `uv run slackchat "text"`
- Eval suite: `uv run slackchat eval`
- Daemon: `uv run slackchat serve`

Required order before claiming done: `uv run pytest` then `uv run lint-imports`.

## Architecture

`core/` and `providers/` are the inner layers. They must not import `cli/`,
`server/`, `eval/`, `store/`, `service`, or `config`. `core/` reaches the
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

## The constraint that matters

Correction mode must not over-edit. A sentence that is already correct comes
back byte-for-byte. The `unchanged` group in the eval suite measures exactly
this, and it is the project's primary metric. Never loosen an `unchanged`
case to make a run go green.
