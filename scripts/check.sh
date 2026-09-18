#!/usr/bin/env bash
# Canonical check sequence for slackchat. AGENTS.md, the git-commit skill,
# and CI all call this instead of restating the command list.
set -euo pipefail
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run lint-imports
