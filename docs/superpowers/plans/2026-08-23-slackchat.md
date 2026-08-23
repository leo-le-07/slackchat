# slackchat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only text tool with one core service that either fixes errors in English text without over-editing, or translates Vietnamese to natural English under a fixed voice constraint, exposed through a CLI in Phase 1 and a local HTTP daemon ready for a Phase 2 browser extension.

**Architecture:** Everything funnels through one pure-ish function `core.pipeline.process()`. Language detection, diffing, sanitising and validation are deterministic and testable without an API key. `slackchat.service` is the single wiring layer (build provider from config → call `process()` → write the log row); CLI, server and eval runner all go through it, so no second code path can exist. Architecture boundaries are enforced in CI by `import-linter`.

**Tech Stack:** Python 3.14, `uv` (with the `uv_build` backend), stdlib `sqlite3` / `difflib` / `tomllib` / `argparse`, `anthropic` 1.x SDK, FastAPI + uvicorn, `pyyaml` for eval cases, `pytest`, `import-linter`, `httpx` (dev only, for FastAPI's `TestClient`).

**Spec:** `docs/superpowers/specs/2026-08-22-slackchat-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The number one product constraint:** correction mode must not over-edit. A sentence that is already correct must come back byte-for-byte. Every design decision below serves making that measurable and enforceable.
- Output rules, both modes: no emoji; no AI-generated em dash (U+2014); no AI-generated semicolon; keep tone and relative length; translation adds no idea absent from the source.
- Python version: `requires-python = ">=3.14"`. Verified locally: CPython 3.14.2, uv 0.9.17.
- Pinned dependency floors, all verified resolvable on 2026-08-23: `anthropic>=1.0.0`, `fastapi>=0.141.1`, `uvicorn>=0.52.4`, `pyyaml>=6.0.3`. Dev: `pytest>=9.1.1`, `import-linter>=2.13`, `httpx>=0.28.1`.
- Model id: **`claude-haiku-4-5`**. Pricing: **$1.00 / 1M input tokens, $5.00 / 1M output tokens**.
- API key comes from the `ANTHROPIC_API_KEY` environment variable only. Never write it into a config file, a log row, or a test fixture.
- `anthropic` 1.x is built on `httpx2`, not `httpx`. Never `import httpx` in package code.
- Haiku 4.5 is a pre-4.6 model: do **not** send `thinking`, and do **not** send `output_config.effort` — `effort` is rejected on Haiku 4.5.
- Import rules, enforced by `lint-imports` in CI: `core/` and `providers/` must not import `cli/`, `server/`, `eval/`, `store/`, `service`, or `config`. `core/` may import `providers.base` (the Protocol) but never `providers.anthropic`.
- `cost_usd` is `NULL` when the model is missing from the price table, never `0.0`.
- Every task ends with a green `uv run pytest` and a green `uv run lint-imports`.
- Commit at the end of every task. Conventional-commit prefixes (`feat:`, `test:`, `chore:`).

## Corrections to the spec, applied in this plan

Three points in the spec are wrong or under-specified. Each is corrected here with the reason, so an executor does not "fix" the plan back to the spec.

1. **Model id has no date suffix.** Spec §9 states the "full model id" is `claude-haiku-4-5-20251001` and that the price table must be keyed on that dated string because it is what the API returns in `response.model`. The current model id is `claude-haiku-4-5`, complete as-is — date suffixes are not appended to current model ids. The spec's *reasoning* is right though: the table must be keyed on what the API actually returns. Task 6 therefore keys on `claude-haiku-4-5` **and** normalises a trailing `-YYYYMMDD` off whatever `response.model` contains before lookup, so both forms resolve. Pricing values ($1 / $5 per MTok) are correct as specified.
2. **One extra table, `eval_results`.** Spec §8.1 claims `--compare A B` is "just a SQL query", but the §7 schema stores no per-assertion outcome, so pass rate is not derivable from `runs`. Task 12 adds `eval_results(run_id, case_id, check_name, passed)`. `runs` and `reviews` stay exactly as specified.
3. **Server token storage.** Spec §11 says the generated token is saved "into config". There is no TOML writer in the stdlib, and appending a `[server]` table to a file that already has one makes it unparseable. Task 14 therefore reads `[server] token` from `config.toml` if the user set it by hand, and otherwise generates and persists to `~/.config/slackchat/server_token` — same config directory, no risk of corrupting a hand-edited file.

Also note, three smaller reconciliations:

- **`max_length_ratio` is an eval assertion, not a pipeline gate.** It lives in `[limits]` (spec §9), but spec §5.3 lists only three validate checks and its flag list has no entry for length. So it is implemented only as automatic eval assertion four (spec §8.1), and no flag is invented for it.
- **`empty_output` is a fourth flag.** Spec §5.3 makes "output rỗng" a validate check but omits it from the flag list. A check with no flag cannot be seen in the log, so `empty_output` is added.
- **`pyyaml` is a dependency.** Spec §13's tech-stack list omits it, but §8.1 defines cases as `eval/cases/*.yaml`. One small parser beats hand-rolling YAML or contradicting §8.1.

---

## File Structure

```
pyproject.toml                    project metadata, deps, script entry point, import-linter contracts
AGENTS.md                         commands and conventions for future agents
src/slackchat/
  __init__.py                     empty
  config.py                       TOML load, path resolution, Config dataclasses
  service.py                      the only wiring layer: provider + process() + log write
  core/
    types.py                      Mode, Change, Result, Limits, EmptyInputError
    detect.py                     pure Vietnamese/English detection
    diffing.py                    word-level difflib diff, changed_ratio
    validate.py                   sanitize, violations, mechanical fallback
    prompts.py                    frontmatter parse, {{VOICE}} resolve, version + hash
    pipeline.py                   process() — the single entry point
  providers/
    base.py                       Provider Protocol, Completion, ProviderError
    anthropic.py                  AnthropicProvider
    pricing.py                    price table (data) + cost_usd()
  prompts/
    correction.md                 correction template, {{VOICE}} placeholder
    translation.md                translation template, {{VOICE}} placeholder
    voice.md                      the user's voice constraint, verbatim
  store/
    schema.sql                    runs, reviews, eval_results, indexes
    sqlite.py                     connect (WAL), insert_run, queries, reviews, eval_results
  eval/
    assertions.py                 Case loading, universal + declared checks
    runner.py                     run cases, print pass rate + cost, --compare, --review
    rubric.md                     0/1/2 anchors with examples, versioned
    cases/correction.yaml         correction cases, unchanged group first
    cases/translation.yaml        translation cases
  cli/
    main.py                       argv dispatch, subcommands, one-shot, exit codes
    render.py                     coloured inline diff, metadata line, flag lines
    repl.py                       multi-line REPL loop
    banner.py                     hardcoded bitmap SLACKCHAT wordmark
    clipboard.py                  pbcopy via subprocess
  server/
    app.py                        FastAPI app, token auth, CORS, /process, /health
tests/                            one test module per source module
extension/.gitkeep                Phase 2 placeholder, empty in Phase 1
```

Every directory under `src/slackchat/` gets an `__init__.py` in Task 1 — including ones whose real content lands much later — so that `lint-imports` contracts resolve from the first task onward.

---

### Task 1: Project scaffold, core types, language detection

Covers spec slice 1. No API key needed. Scaffolding (pyproject, package skeleton, import-linter contracts, AGENTS.md) is folded in here because `detect` is the first thing that needs it.

**Files:**
- Create: `pyproject.toml`
- Create: `src/slackchat/__init__.py`, `src/slackchat/core/__init__.py`, `src/slackchat/providers/__init__.py`, `src/slackchat/store/__init__.py`, `src/slackchat/eval/__init__.py`, `src/slackchat/cli/__init__.py`, `src/slackchat/server/__init__.py` (all empty)
- Create: `src/slackchat/core/types.py`
- Create: `src/slackchat/core/detect.py`
- Create: `extension/.gitkeep` (empty)
- Modify: `AGENTS.md` (replace whole file)
- Test: `tests/test_detect.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `slackchat.core.types.Mode = Literal["correction", "translation"]`
  - `slackchat.core.types.Change` — frozen dataclass, fields `kind: Literal["equal","insert","delete","replace"]`, `before: str`, `after: str`
  - `slackchat.core.types.Limits` — frozen dataclass, fields `max_changed_ratio: float`, `max_length_ratio: float`, `max_retries: int`
  - `slackchat.core.types.Result` — frozen dataclass, exactly the fields in spec §5.4
  - `slackchat.core.types.EmptyInputError(ValueError)`
  - `slackchat.core.detect.detect(text: str) -> Mode`
  - `slackchat.core.detect.LOANWORDS: tuple[str, ...]`

- [ ] **Step 1: Write `pyproject.toml`**

`Limits` lives in `core/types.py`, not `config.py`, so that `core/` never imports `config` — that is why the third contract below can forbid it.

```toml
[project]
name = "slackchat"
version = "0.1.0"
description = "Local English correction and Vietnamese-to-English translation"
requires-python = ">=3.14"
dependencies = [
    "anthropic>=1.0.0",
    "fastapi>=0.141.1",
    "uvicorn>=0.52.4",
    "pyyaml>=6.0.3",
]

[project.scripts]
slackchat = "slackchat.cli.main:main"

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "import-linter>=2.13",
    "httpx>=0.28.1",
]

[build-system]
requires = ["uv_build>=0.9,<0.10"]
build-backend = "uv_build"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.importlinter]
root_package = "slackchat"

[[tool.importlinter.contracts]]
name = "core does not depend on outer layers"
type = "forbidden"
source_modules = ["slackchat.core"]
forbidden_modules = [
    "slackchat.cli",
    "slackchat.server",
    "slackchat.eval",
    "slackchat.store",
    "slackchat.service",
    "slackchat.config",
]

[[tool.importlinter.contracts]]
name = "core reaches providers only through the protocol"
type = "forbidden"
source_modules = ["slackchat.core"]
forbidden_modules = ["slackchat.providers.anthropic", "slackchat.providers.pricing"]

[[tool.importlinter.contracts]]
name = "providers do not depend on outer layers"
type = "forbidden"
source_modules = ["slackchat.providers"]
forbidden_modules = [
    "slackchat.cli",
    "slackchat.server",
    "slackchat.eval",
    "slackchat.store",
    "slackchat.service",
    "slackchat.config",
    "slackchat.core",
]
```

- [ ] **Step 2: Create the empty package skeleton and sync**

```bash
mkdir -p src/slackchat/{core,providers,prompts,store,eval/cases,cli,server} tests extension
for d in "" /core /providers /store /eval /cli /server; do : > "src/slackchat$d/__init__.py"; done
: > extension/.gitkeep
uv sync
```

Run: `uv run python -c "import slackchat, slackchat.core, slackchat.cli; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Write the failing detection test**

`tests/test_detect.py`. The table is the deliverable of this task — it is the only thing standing between the tool and silently translating English or "correcting" Vietnamese.

```python
import pytest

from slackchat.core.detect import detect

VIETNAMESE = [
    "Tôi đã hoàn thành task hôm qua.",
    "Cà phê ở đây ngon.",
    "Em gửi anh bản cập nhật.",
    "Mai họp lúc 3 giờ nhé",
    "Kiều Anh sẽ review lại",
    "Số liệu này chưa khớp",
    "Cà phê sáng nay hơi đắng",
    "À, tôi hiểu rồi",
    # Vietnamese sentence that also contains an English loanword
    "Tôi đi café với Linh.",
]

ENGLISH = [
    "The deployment failed because the config was missing.",
    "I has finish the task yesterday.",
    # Unaccented Vietnamese-looking English is still treated as English:
    # the user commits to always typing Vietnamese with diacritics.
    "Anh oi, minh can them mot seat nua.",
    "Vui long kiem tra lai",
    # Accented English loanwords must not trip detection
    "Let's meet at the café after standup.",
    "Please attach your résumé and a short cliché-free intro.",
    "That is a naïve assumption about the façade.",
    "We had déjà vu over the crème brûlée invoice.",
    "Order à la carte, not the set menu.",
    "The rôle of the protégé is unclear.",
]


@pytest.mark.parametrize("text", VIETNAMESE)
def test_vietnamese_routes_to_translation(text):
    assert detect(text) == "translation"


@pytest.mark.parametrize("text", ENGLISH)
def test_english_routes_to_correction(text):
    assert detect(text) == "correction"


def test_decomposed_diacritics_are_normalised():
    # "Tôi" written as T + o + combining circumflex + i
    assert detect("Tôi đã xong") == "translation"


def test_empty_and_whitespace_default_to_correction():
    assert detect("") == "correction"
    assert detect("   \n ") == "correction"


def test_exclusive_letter_alone_is_decisive():
    # A single 'đ' is proof enough, no allowlist consultation
    assert detect("đ") == "translation"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/test_detect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.core.detect'`

- [ ] **Step 5: Write `src/slackchat/core/types.py`**

```python
"""Data types shared across the whole system. No behaviour lives here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["correction", "translation"]
ChangeKind = Literal["equal", "insert", "delete", "replace"]


class EmptyInputError(ValueError):
    """Raised for empty or whitespace-only input, before any provider call."""


@dataclass(frozen=True)
class Change:
    """One word-level diff segment.

    ``equal`` segments are kept in ``Result.changes`` on purpose: they are what
    lets the CLI render an inline diff, and what lets the Phase 2 extension do
    the same from the JSON alone, without re-running the diff.
    """

    kind: ChangeKind
    before: str
    after: str


@dataclass(frozen=True)
class Limits:
    """Numeric gates. Lives in core so that core never imports config."""

    max_changed_ratio: float = 0.25
    max_length_ratio: float = 1.5
    max_retries: int = 1


@dataclass(frozen=True)
class Result:
    run_id: str
    original: str
    output: str
    mode: Mode
    forced: bool
    changes: list[Change]
    changed_ratio: float
    flags: list[str]
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    created_at: str
    error: str | None
```

- [ ] **Step 6: Write `src/slackchat/core/detect.py`**

Two tiers, as the spec requires. Tier one letters exist in no English loanword, so their presence decides immediately and the allowlist is never consulted. Tier two letters overlap with French and Portuguese borrowings, so allowlisted loanwords are removed before scoring.

```python
"""Deterministic Vietnamese/English detection. Pure, no network, no LLM."""

from __future__ import annotations

import re
import unicodedata

from slackchat.core.types import Mode

# Letters that occur in Vietnamese and in no English loanword. Decisive on sight.
VN_EXCLUSIVE = frozenset("ăằắẳẵặơờớởỡợưừứửữựđ")

# Letters that occur in Vietnamese but also in borrowed English spellings.
# Only counted after allowlisted loanwords are removed.
VN_MARKED = frozenset(
    "áàảãạ"
    "âầấẩẫậ"
    "éèẻẽẹ"
    "êềếểễệ"
    "íìỉĩị"
    "óòỏõọ"
    "ôồốổỗộ"
    "úùủũụ"
    "ýỳỷỹỵ"
)

# Accented words an English writer may legitimately type. Kept deliberately
# small: only entries whose accents fall inside VN_MARKED can ever matter.
LOANWORDS: tuple[str, ...] = (
    "café", "cafés", "canapé", "château", "cliché", "clichés", "cortège",
    "crème brûlée", "crème", "brûlée", "crêpe", "crêpes", "décor", "déjà vu",
    "déjà", "début", "débuts", "éclair", "élite", "entrée", "entrées",
    "exposé", "façade", "fête", "fiancé", "fiancée", "matériel", "mêlée",
    "naïveté", "papier-mâché", "pâté", "pièce", "protégé", "protégée",
    "résumé", "résumés", "rôle", "séance", "soirée", "soupçon", "touché",
    "à la carte", "tête-à-tête", "vis-à-vis", "apéritif",
)

# Longest-first so "crème brûlée" wins over "crème". Lookarounds instead of \b
# so that hyphenated entries such as "vis-à-vis" match as a whole.
_LOANWORD_RE = re.compile(
    r"(?<!\w)(?:%s)(?!\w)"
    % "|".join(sorted((re.escape(w) for w in LOANWORDS), key=len, reverse=True)),
    re.IGNORECASE,
)


def detect(text: str) -> Mode:
    """Return the mode implied by ``text``.

    Vietnamese input means translation mode. Anything else means correction
    mode. There is no grey zone and no clarifying prompt: ``--mode`` is the
    only escape hatch.
    """
    normalised = unicodedata.normalize("NFC", text).lower()
    if VN_EXCLUSIVE & frozenset(normalised):
        return "translation"
    without_loanwords = _LOANWORD_RE.sub(" ", normalised)
    if VN_MARKED & frozenset(without_loanwords):
        return "translation"
    return "correction"
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_detect.py -q`
Expected: PASS, 24 tests.

- [ ] **Step 8: Run the import contracts**

Run: `uv run lint-imports`
Expected: `Contracts: 3 kept, 0 broken.`

- [ ] **Step 9: Replace `AGENTS.md`**

```markdown
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
```

- [ ] **Step 10: Commit**

```bash
printf '.venv/\n__pycache__/\n*.pyc\n.env\n.pytest_cache/\nuv.lock merge=binary\n' > /dev/null  # no-op reminder: .gitignore already covers .venv, __pycache__, *.pyc, .env
git add pyproject.toml uv.lock AGENTS.md src tests extension
git commit -m "feat: scaffold slackchat package with core types and language detection"
```

If `.pytest_cache/` shows up as untracked, add it to `.gitignore` in this commit.

---

### Task 2: Config loading and path resolution

**Files:**
- Create: `src/slackchat/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `slackchat.core.types.Limits`
- Produces:
  - `slackchat.config.ProviderConfig(name: str, model: str)` — frozen
  - `slackchat.config.CliConfig(auto_copy: bool)` — frozen
  - `slackchat.config.ServerConfig(port: int, token: str | None, allowed_origins: tuple[str, ...])` — frozen
  - `slackchat.config.Config(provider, limits, cli, server)` — frozen
  - `slackchat.config.load_config(path: Path | None = None) -> Config`
  - `slackchat.config.config_dir() -> Path`
  - `slackchat.config.config_path() -> Path`
  - `slackchat.config.db_path() -> Path`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`. The env overrides exist so every later test can point config and database at `tmp_path`.

```python
from pathlib import Path

import pytest

from slackchat import config as cfg


def test_defaults_when_no_file(tmp_path):
    conf = cfg.load_config(tmp_path / "missing.toml")
    assert conf.provider.name == "anthropic"
    assert conf.provider.model == "claude-haiku-4-5"
    assert conf.limits.max_changed_ratio == 0.25
    assert conf.limits.max_length_ratio == 1.5
    assert conf.limits.max_retries == 1
    assert conf.cli.auto_copy is True
    assert conf.server.port == 8765
    assert conf.server.token is None
    assert conf.server.allowed_origins == ()


def test_full_file_is_read(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        """
[provider]
name  = "anthropic"
model = "claude-haiku-4-5"

[limits]
max_changed_ratio = 0.4
max_length_ratio  = 2.0
max_retries       = 2

[cli]
auto_copy = false

[server]
port = 9000
token = "abc123"
allowed_origins = ["chrome-extension://aaaa"]
""",
        encoding="utf-8",
    )
    conf = cfg.load_config(p)
    assert conf.limits.max_changed_ratio == 0.4
    assert conf.limits.max_retries == 2
    assert conf.cli.auto_copy is False
    assert conf.server.port == 9000
    assert conf.server.token == "abc123"
    assert conf.server.allowed_origins == ("chrome-extension://aaaa",)


def test_partial_file_falls_back_per_key(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[limits]\nmax_retries = 3\n", encoding="utf-8")
    conf = cfg.load_config(p)
    assert conf.limits.max_retries == 3
    assert conf.limits.max_changed_ratio == 0.25  # untouched default
    assert conf.provider.model == "claude-haiku-4-5"


def test_config_path_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SLACKCHAT_CONFIG", str(tmp_path / "x" / "c.toml"))
    assert cfg.config_path() == tmp_path / "x" / "c.toml"


def test_config_path_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("SLACKCHAT_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cfg.config_path() == tmp_path / "slackchat" / "config.toml"


def test_db_path_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SLACKCHAT_DB", str(tmp_path / "runs.db"))
    assert cfg.db_path() == tmp_path / "runs.db"


def test_db_path_default_location(monkeypatch, tmp_path):
    monkeypatch.delenv("SLACKCHAT_DB", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert cfg.db_path() == tmp_path / "slackchat" / "runs.db"


def test_malformed_toml_raises_with_the_path_in_the_message(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[limits\n", encoding="utf-8")
    with pytest.raises(cfg.ConfigError) as excinfo:
        cfg.load_config(p)
    assert str(p) in str(excinfo.value)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL — `ImportError` / `AttributeError: module 'slackchat.config' has no attribute 'load_config'`

- [ ] **Step 3: Write `src/slackchat/config.py`**

```python
"""Config loading. Defaults live here; the file only overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from slackchat.core.types import Limits

DEFAULT_MODEL = "claude-haiku-4-5"


class ConfigError(RuntimeError):
    """Raised when the config file exists but cannot be parsed."""


@dataclass(frozen=True)
class ProviderConfig:
    name: str = "anthropic"
    model: str = DEFAULT_MODEL


@dataclass(frozen=True)
class CliConfig:
    auto_copy: bool = True


@dataclass(frozen=True)
class ServerConfig:
    port: int = 8765
    token: str | None = None
    allowed_origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    provider: ProviderConfig = ProviderConfig()
    limits: Limits = Limits()
    cli: CliConfig = CliConfig()
    server: ServerConfig = ServerConfig()


def _xdg(env_var: str, fallback: str) -> Path:
    raw = os.environ.get(env_var)
    return Path(raw) if raw else Path.home() / fallback


def config_dir() -> Path:
    """Directory holding config.toml and the server token file."""
    explicit = os.environ.get("SLACKCHAT_CONFIG")
    if explicit:
        return Path(explicit).parent
    return _xdg("XDG_CONFIG_HOME", ".config") / "slackchat"


def config_path() -> Path:
    explicit = os.environ.get("SLACKCHAT_CONFIG")
    if explicit:
        return Path(explicit)
    return config_dir() / "config.toml"


def db_path() -> Path:
    explicit = os.environ.get("SLACKCHAT_DB")
    if explicit:
        return Path(explicit)
    return _xdg("XDG_DATA_HOME", ".local/share") / "slackchat" / "runs.db"


def load_config(path: Path | None = None) -> Config:
    """Read config from ``path`` (default: :func:`config_path`).

    A missing file is not an error: every value has a default. A malformed
    file is an error, because silently falling back would hide a typo in a
    limit that guards the number one constraint.
    """
    target = path if path is not None else config_path()
    if not target.exists():
        return Config()
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"cannot parse {target}: {exc}") from exc

    provider_raw = raw.get("provider", {})
    limits_raw = raw.get("limits", {})
    cli_raw = raw.get("cli", {})
    server_raw = raw.get("server", {})

    defaults = Config()
    return Config(
        provider=ProviderConfig(
            name=provider_raw.get("name", defaults.provider.name),
            model=provider_raw.get("model", defaults.provider.model),
        ),
        limits=Limits(
            max_changed_ratio=float(
                limits_raw.get("max_changed_ratio", defaults.limits.max_changed_ratio)
            ),
            max_length_ratio=float(
                limits_raw.get("max_length_ratio", defaults.limits.max_length_ratio)
            ),
            max_retries=int(limits_raw.get("max_retries", defaults.limits.max_retries)),
        ),
        cli=CliConfig(auto_copy=bool(cli_raw.get("auto_copy", defaults.cli.auto_copy))),
        server=ServerConfig(
            port=int(server_raw.get("port", defaults.server.port)),
            token=server_raw.get("token", defaults.server.token),
            allowed_origins=tuple(server_raw.get("allowed_origins", ())),
        ),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_config.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 5: Verify the boundary still holds**

Run: `uv run lint-imports`
Expected: `Contracts: 3 kept, 0 broken.` (`config` imports `core.types`, which is the allowed direction.)

- [ ] **Step 6: Commit**

```bash
git add src/slackchat/config.py tests/test_config.py
git commit -m "feat: add config loading with XDG paths and env overrides"
```

---

### Task 3: Word-level diff and changed_ratio

`changed_ratio` is the instrument that makes over-edit measurable, so it gets its own task and its own arithmetic tests.

**Files:**
- Create: `src/slackchat/core/diffing.py`
- Test: `tests/test_diffing.py`

**Interfaces:**
- Consumes: `slackchat.core.types.Change`
- Produces:
  - `slackchat.core.diffing.tokenize(text: str) -> list[str]`
  - `slackchat.core.diffing.diff_words(original: str, output: str) -> tuple[list[Change], float]`
  - `slackchat.core.diffing.word_count(text: str) -> int`

- [ ] **Step 1: Write the failing test**

```python
from slackchat.core.diffing import diff_words, tokenize, word_count


def test_tokenize_splits_on_whitespace_only():
    assert tokenize("Hi a @ka, is that okay?") == ["Hi", "a", "@ka,", "is", "that", "okay?"]
    assert tokenize("  spaced \n out  ") == ["spaced", "out"]
    assert tokenize("") == []


def test_identical_text_is_all_equal_and_zero_ratio():
    changes, ratio = diff_words("The deployment failed.", "The deployment failed.")
    assert ratio == 0.0
    assert [c.kind for c in changes] == ["equal"]
    assert changes[0].before == "The deployment failed."


def test_two_word_fix_in_a_six_word_sentence():
    changes, ratio = diff_words(
        "I has finish the task yesterday.", "I finished the task yesterday."
    )
    assert [c.kind for c in changes] == ["equal", "replace", "equal"]
    assert changes[1].before == "has finish"
    assert changes[1].after == "finished"
    # replace of 2 tokens by 1 counts as max(2, 1) = 2 changed, over 6 input tokens
    assert ratio == 0.3333


def test_pure_insertion_counts_inserted_tokens():
    changes, ratio = diff_words("Deploy done", "Deploy is done")
    assert [c.kind for c in changes] == ["equal", "insert", "equal"]
    assert changes[1].before == ""
    assert changes[1].after == "is"
    assert ratio == 0.5  # 1 inserted / 2 input tokens


def test_pure_deletion_counts_deleted_tokens():
    changes, ratio = diff_words("Deploy is really done", "Deploy is done")
    assert [c.kind for c in changes] == ["equal", "delete", "equal"]
    assert changes[1].before == "really"
    assert changes[1].after == ""
    assert ratio == 0.25


def test_ratio_can_exceed_one_when_output_balloons():
    _, ratio = diff_words("hello", "Greetings and salutations to you my friend")
    assert ratio == 7.0


def test_empty_original_with_output_is_ratio_one():
    _, ratio = diff_words("", "something appeared")
    assert ratio == 1.0


def test_both_empty_is_ratio_zero():
    changes, ratio = diff_words("", "")
    assert changes == []
    assert ratio == 0.0


def test_word_count():
    assert word_count("one two three") == 3
    assert word_count("") == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_diffing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.core.diffing'`

- [ ] **Step 3: Write `src/slackchat/core/diffing.py`**

```python
"""Word-level diff. Local, free, and incapable of hallucinating a change."""

from __future__ import annotations

import difflib
import re

from slackchat.core.types import Change

_TOKEN_RE = re.compile(r"\S+")


def tokenize(text: str) -> list[str]:
    """Split on whitespace. Punctuation stays attached to its word.

    Keeping punctuation attached means "okay." vs "okay?" counts as one
    changed token, which is what a reader would call one change.
    """
    return _TOKEN_RE.findall(text)


def word_count(text: str) -> int:
    return len(tokenize(text))


def diff_words(original: str, output: str) -> tuple[list[Change], float]:
    """Return every diff segment (including ``equal``) and the changed ratio.

    ``changed_ratio`` is changed tokens over input tokens. A replace of n
    tokens by m counts as ``max(n, m)``: rewriting three words as one is not
    cheaper than rewriting one word as three.
    """
    before_tokens = tokenize(original)
    after_tokens = tokenize(output)
    matcher = difflib.SequenceMatcher(a=before_tokens, b=after_tokens, autojunk=False)

    changes: list[Change] = []
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        segment = Change(
            kind=tag,  # type: ignore[arg-type]
            before=" ".join(before_tokens[i1:i2]),
            after=" ".join(after_tokens[j1:j2]),
        )
        changes.append(segment)
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)

    if before_tokens:
        ratio = changed / len(before_tokens)
    else:
        ratio = 1.0 if after_tokens else 0.0
    return changes, round(ratio, 4)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_diffing.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/core/diffing.py tests/test_diffing.py
git commit -m "feat: add word-level diff and changed_ratio"
```

---

### Task 4: Sanitize, violations, and the mechanical fallback

Layer two and three of the three-layer over-edit defence (spec §3, §5.3). Pure functions only — the retry *loop* is Task 7.

**Files:**
- Create: `src/slackchat/core/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `slackchat.core.types.Mode`
- Produces:
  - `slackchat.core.validate.Violation(flag: str, instruction: str)` — frozen
  - `slackchat.core.validate.sanitize(text: str) -> str`
  - `slackchat.core.validate.banned_chars_introduced(original: str, output: str, mode: Mode) -> list[str]`
  - `slackchat.core.validate.find_violations(*, original, output, mode, changed_ratio, max_changed_ratio) -> list[Violation]`
  - `slackchat.core.validate.mechanical_replace(text: str) -> str`
  - `slackchat.core.validate.retry_suffix(violations: list[Violation]) -> str`
  - Flag constants: `FLAG_OVER_EDIT = "over_edit_suspected"`, `FLAG_BANNED_CHAR = "banned_char_introduced"`, `FLAG_RETRIED = "retried"`, `FLAG_MECHANICAL = "mechanical_fallback"`, `FLAG_UNKNOWN_PRICING = "unknown_pricing"`, `FLAG_EMPTY_OUTPUT = "empty_output"`
  - `BANNED_CHARS = (";", "—")`

`FLAG_EMPTY_OUTPUT` is not in the spec's §5.3 flag list, but §5.3 does list "output rỗng" as validate's third check, and a check with no flag cannot be observed in the log. It is added deliberately.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from slackchat.core.validate import (
    BANNED_CHARS,
    FLAG_BANNED_CHAR,
    FLAG_EMPTY_OUTPUT,
    FLAG_OVER_EDIT,
    banned_chars_introduced,
    find_violations,
    mechanical_replace,
    retry_suffix,
    sanitize,
)


# --- sanitize ---------------------------------------------------------------

def test_sanitize_removes_emoji_and_tidies_the_gap():
    assert sanitize("Thanks! 🙏 Looks good ✅") == "Thanks! Looks good"


def test_sanitize_removes_emoji_with_variation_selector():
    assert sanitize("Second line ✈️  here") == "Second line here"


def test_sanitize_preserves_newlines():
    assert sanitize("one 🎉\ntwo") == "one\ntwo"


def test_sanitize_leaves_ordinary_punctuation_alone():
    text = "It costs 30° and 50% — fine; ok…"
    assert sanitize(text) == text


def test_sanitize_strips_leading_and_trailing_whitespace():
    assert sanitize("  hello  \n") == "hello"


def test_sanitize_never_touches_semicolon_or_em_dash():
    # Mechanical substitution of these guesses; sanitize must not guess.
    assert ";" in sanitize("a; b")
    assert "—" in sanitize("a — b")


# --- banned characters ------------------------------------------------------

def test_banned_chars_are_ordered_and_deduped():
    assert BANNED_CHARS == (";", "—")


def test_correction_keeps_the_writers_own_em_dash():
    assert banned_chars_introduced("I shipped it — finally.", "I shipped it — finally.", "correction") == []


def test_correction_flags_an_em_dash_the_model_added():
    assert banned_chars_introduced("I shipped it finally.", "I shipped it — finally.", "correction") == ["—"]


def test_correction_flags_a_semicolon_the_model_added():
    assert banned_chars_introduced("Deploy failed. Rollback done.", "Deploy failed; rollback done.", "correction") == [";"]


def test_translation_bans_unconditionally_even_if_the_source_had_one():
    assert banned_chars_introduced("Tôi xong; anh xem nhé", "I am done; please review", "translation") == [";"]


# --- find_violations --------------------------------------------------------

def test_clean_correction_has_no_violations():
    assert find_violations(
        original="The deployment failed.",
        output="The deployment failed.",
        mode="correction",
        changed_ratio=0.0,
        max_changed_ratio=0.25,
    ) == []


def test_over_edit_above_the_limit_is_flagged():
    violations = find_violations(
        original="The deployment failed because the config was missing.",
        output="Unfortunately, the deployment was unsuccessful due to a missing configuration.",
        mode="correction",
        changed_ratio=0.75,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_OVER_EDIT]
    assert "byte-for-byte" in violations[0].instruction


def test_over_edit_is_not_checked_in_translation_mode():
    assert find_violations(
        original="Tôi đã hoàn thành task hôm qua.",
        output="I finished the task yesterday.",
        mode="translation",
        changed_ratio=3.0,
        max_changed_ratio=0.25,
    ) == []


def test_ratio_exactly_at_the_limit_passes():
    assert find_violations(
        original="a b c d",
        output="a b c e",
        mode="correction",
        changed_ratio=0.25,
        max_changed_ratio=0.25,
    ) == []


def test_empty_output_short_circuits_every_other_check():
    violations = find_violations(
        original="something",
        output="   ",
        mode="correction",
        changed_ratio=1.0,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_EMPTY_OUTPUT]


def test_multiple_banned_chars_share_one_flag_but_give_two_instructions():
    violations = find_violations(
        original="Deploy failed. Rollback done. All good.",
        output="Deploy failed; rollback done — all good.",
        mode="correction",
        changed_ratio=0.1,
        max_changed_ratio=0.25,
    )
    assert [v.flag for v in violations] == [FLAG_BANNED_CHAR, FLAG_BANNED_CHAR]
    assert "semicolon" in violations[0].instruction
    assert "em dash" in violations[1].instruction


# --- retry suffix -----------------------------------------------------------

def test_retry_suffix_lists_each_instruction():
    violations = find_violations(
        original="Deploy failed. Rollback done.",
        output="Deploy failed; rollback done.",
        mode="correction",
        changed_ratio=0.1,
        max_changed_ratio=0.25,
    )
    suffix = retry_suffix(violations)
    assert suffix.startswith("\n\n")
    assert "rejected" in suffix
    assert suffix.count("\n- ") == 1


def test_retry_suffix_is_empty_without_violations():
    assert retry_suffix([]) == ""


# --- mechanical fallback ----------------------------------------------------

@pytest.mark.parametrize(
    "given,expected",
    [
        ("We shipped it — the tests passed; all good.", "We shipped it, the tests passed, all good."),
        ("Deploy failed; rollback done.", "Deploy failed, rollback done."),
        ("It works—mostly.", "It works, mostly."),
        ("a — ; b", "a, b"),
        ("Steps:\n- one;\n- two — three", "Steps:\n- one,\n- two, three"),
        ("nothing to do here", "nothing to do here"),
    ],
)
def test_mechanical_replace(given, expected):
    assert mechanical_replace(given) == expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_validate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.core.validate'`

- [ ] **Step 3: Write `src/slackchat/core/validate.py`**

```python
"""Sanitising and validation: layers two and three of the over-edit defence.

Sanitize does the one substitution that cannot be wrong (deleting emoji).
Validate only *detects*; the retry loop lives in the pipeline. Mechanical
replacement is the last resort, and it always leaves a flag behind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from slackchat.core.types import Mode

FLAG_OVER_EDIT = "over_edit_suspected"
FLAG_BANNED_CHAR = "banned_char_introduced"
FLAG_RETRIED = "retried"
FLAG_MECHANICAL = "mechanical_fallback"
FLAG_UNKNOWN_PRICING = "unknown_pricing"
FLAG_EMPTY_OUTPUT = "empty_output"

EM_DASH = "—"
SEMICOLON = ";"
BANNED_CHARS: tuple[str, ...] = (SEMICOLON, EM_DASH)

_BANNED_NAMES = {SEMICOLON: "semicolon", EM_DASH: "em dash"}

# Emoji blocks. Deliberately excludes U+2013/U+2014 (dashes), U+2026 (ellipsis),
# U+00B0 (degree) and U+2018-201D (quotes), which are legitimate prose.
_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # emoticons, pictographs, flags, extended symbols
    "\U00002600-\U000026ff"  # miscellaneous symbols
    "\U00002700-\U000027bf"  # dingbats
    "\U00002b00-\U00002bff"  # miscellaneous symbols and arrows
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U000020e3"  # combining enclosing keycap
    "]+"
)


@dataclass(frozen=True)
class Violation:
    flag: str
    instruction: str


def sanitize(text: str) -> str:
    """Delete emoji, then tidy only the whitespace the deletion created.

    Newlines survive: REPL input is multi-line and reflowing it would itself
    be an edit.
    """
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+(?=\n)", "", cleaned)
    return cleaned.strip()


def banned_chars_introduced(original: str, output: str, mode: Mode) -> list[str]:
    """Which banned characters count as violations, in ``BANNED_CHARS`` order.

    In correction mode a banned character only counts if the model introduced
    it. Deleting one the writer typed themselves would be over-editing. In
    translation mode the output is wholly model-written, so the ban is
    absolute.
    """
    hits = []
    for char in BANNED_CHARS:
        if char not in output:
            continue
        if mode == "translation" or char not in original:
            hits.append(char)
    return hits


def find_violations(
    *,
    original: str,
    output: str,
    mode: Mode,
    changed_ratio: float,
    max_changed_ratio: float,
) -> list[Violation]:
    """Detect every reason to reject ``output``. Empty output short-circuits."""
    if not output.strip():
        return [
            Violation(
                FLAG_EMPTY_OUTPUT,
                "You returned nothing. Return the corrected or translated text.",
            )
        ]

    violations: list[Violation] = []
    for char in banned_chars_introduced(original, output, mode):
        name = _BANNED_NAMES[char]
        violations.append(
            Violation(
                FLAG_BANNED_CHAR,
                f"You used a {name} that was not in the input. "
                f"Rewrite the sentence so it does not need a {name}.",
            )
        )

    if mode == "correction" and changed_ratio > max_changed_ratio:
        violations.append(
            Violation(
                FLAG_OVER_EDIT,
                "You changed too much of the input. Undo every edit that was "
                "not fixing an actual error. Any sentence that was already "
                "correct must come back byte-for-byte.",
            )
        )
    return violations


def retry_suffix(violations: list[Violation]) -> str:
    """Build the extra instruction appended to the *user* message on retry.

    It goes on the user message, not the system prompt, so that
    ``prompt_hash`` keeps identifying the prompt rather than the attempt.
    """
    if not violations:
        return ""
    lines = [
        "",
        "",
        "Your previous attempt was rejected. Fix exactly these problems and "
        "return only the corrected text:",
    ]
    lines.extend(f"- {v.instruction}" for v in violations)
    return "\n".join(lines)


def mechanical_replace(text: str) -> str:
    """Last-resort banned-character removal. Always sets ``mechanical_fallback``.

    Both banned characters become a comma. A comma is the one substitution
    that needs no capitalisation guess and cannot break a bullet list, which
    is why ``;`` does not become ``.``.
    """
    result = text.replace(EM_DASH, ",").replace(SEMICOLON, ",")
    result = re.sub(r"[ \t]*,", ",", result)  # no space before a comma
    result = re.sub(r",(?=[^\s,])", ", ", result)  # exactly one space after
    result = re.sub(r"(?:,[ \t]*){2,}", ", ", result)  # collapse comma runs
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_validate.py -q`
Expected: PASS, 24 tests.

- [ ] **Step 5: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/core/validate.py tests/test_validate.py
git commit -m "feat: add sanitize, violation detection and mechanical fallback"
```

---

### Task 5: Prompts, voice constraint, versioning and hashing

Layer one of the over-edit defence, plus the versioning that makes eval comparisons honest (spec §6).

**Files:**
- Create: `src/slackchat/prompts/voice.md`
- Create: `src/slackchat/prompts/correction.md`
- Create: `src/slackchat/prompts/translation.md`
- Create: `src/slackchat/core/prompts.py`
- Modify: `pyproject.toml` (ship the `.md` files in the wheel)
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: `slackchat.core.types.Mode`
- Produces:
  - `slackchat.core.prompts.Prompt(mode: Mode, version: str, text: str, hash: str)` — frozen
  - `slackchat.core.prompts.load_prompt(mode: Mode, prompts_dir: Path | None = None) -> Prompt`
  - `slackchat.core.prompts.parse_frontmatter(raw: str) -> tuple[dict[str, str], str]`
  - `slackchat.core.prompts.VOICE_PLACEHOLDER = "{{VOICE}}"`

`Prompt.text` is the resolved system prompt. `Prompt.version` is the template file's own `version:`; `voice.md`'s version is informational only, because the hash already covers its body — that pairing is exactly what spec §6 asks the eval runner to police.

- [ ] **Step 1: Write `src/slackchat/prompts/voice.md`**

Body copied verbatim from `notes.md` § Voice Constraint. Do not reword, reorder, or "improve" any line: the spec (§6, §14) records it as user-supplied content.

```markdown
---
version: 1
---
Formatting Rules
- No emoji
- No em-dash (—)
- No semicolons (;)

Words and Phrases to Cut Entirely
- Greeting/closing filler: "I hope this message finds you well", "please do not hesitate to", "at your earliest convenience", "kindly"
- Corporate transitions: "moving forward", "circle back", "touch base"
- Throat-clearing: "it is important to note that", "it is worth noting that"
- Sentence-opener transitions: "furthermore", "moreover", "additionally"
- Empty/inflated adjectives: "robust", "seamless", "synergy", "holistic", "comprehensive", "cutting-edge", "innovative"
- Intent phrases: "I would like to" (state the ask directly instead)

Replacements
- "in order to" → "to"
- "leverage" / "utilize" → "use"
- "streamline" → "simplify"
- "delve into" → "look into" / "explore"
- "unlock" → "enable" / "allow"
- "elevate" → "improve"
- "foster" → "support" / "encourage"
- "underscore" → "show" / "highlight"

Structural Patterns
- Open directly with context (no greeting preamble unless addressing someone by name)
- Keep "Hi a [@name]" as-is when addressing a senior (this is intentional)
- Use short, direct sentences (typically 1-4 sentences per message)
- End with a direct question when seeking confirmation ("Is that okay?", "Any concerns?", "Is that clear?")
- Use flat bullet lists for multi-step processes (maximum one level of sub-bullets for exceptions or fees)
- Keep natural hedging ("I guess", "I intend to", "I'm afraid", "for now")
- Avoid formal closings like "Best regards" unless present in the source

Non-Goals
- Do not sound like customer support or marketing copy
- Do not add information not present in the source
- Do not convert a casual ask into a formal request
```

- [ ] **Step 2: Write `src/slackchat/prompts/correction.md`**

The closing paragraph exists because the voice constraint reads like a style guide, and a style guide handed to an LLM in a *correction* task is an invitation to rewrite correct sentences.

```markdown
---
version: 1
---
You fix errors in English text. You do not rewrite it.

Return only the corrected text. No preamble, no explanation, no surrounding quotes, no notes.

Rules:
- Fix only grammar, spelling, punctuation errors, and clearly wrong word choice.
- If the text is already correct, return it byte-for-byte unchanged. This is the correct answer more often than not.
- Do not make the text more formal, more polite, or more complete.
- Do not reorder clauses, merge sentences, split sentences, or change paragraph or list structure.
- Do not add information and do not remove information.
- Keep the writer's word choices, contractions, abbreviations, hedges, and informality.
- Keep names, @mentions, URLs, file paths, code, and product names exactly as written.
- Keep the writer's own punctuation, including any em dash or semicolon they typed themselves.
- Never introduce an em dash or a semicolon that was not already in the input.
- Never add emoji.

{{VOICE}}

The voice constraints above describe how this writer already writes. In this task they tell you what not to introduce. They are not permission to rewrite text that is already correct.
```

- [ ] **Step 3: Write `src/slackchat/prompts/translation.md`**

```markdown
---
version: 1
---
You translate Vietnamese text into English.

Return only the English translation. No preamble, no explanation, no surrounding quotes, no notes, no alternative renderings.

Rules:
- Carry over every idea in the source. Add nothing that is not there.
- Write the way a fluent English speaker writes a work chat message, not word by word from the Vietnamese.
- Keep the register of the source. Casual stays casual. A direct ask stays a direct ask.
- Stay close to the source's length. Do not expand.
- Keep names, @mentions, URLs, file paths, code, product names and numbers exactly as written.
- Drop Vietnamese honorifics and particles that carry no English meaning (a, ạ, nhé, ơi), except in the greeting "Hi a @name", which stays as written.
- Never use an em dash or a semicolon.
- Never add emoji.

{{VOICE}}
```

- [ ] **Step 4: Write the failing test**

```python
import hashlib

import pytest

from slackchat.core.prompts import (
    VOICE_PLACEHOLDER,
    load_prompt,
    parse_frontmatter,
)


def test_parse_frontmatter_splits_metadata_from_body():
    meta, body = parse_frontmatter("---\nversion: 3\n---\nhello\nworld\n")
    assert meta == {"version": "3"}
    assert body == "hello\nworld"


def test_parse_frontmatter_tolerates_a_file_without_it():
    meta, body = parse_frontmatter("just a body\n")
    assert meta == {}
    assert body == "just a body"


@pytest.mark.parametrize("mode", ["correction", "translation"])
def test_placeholder_is_resolved(mode):
    prompt = load_prompt(mode)
    assert VOICE_PLACEHOLDER not in prompt.text
    assert "No em-dash" in prompt.text  # the voice body really got inlined
    assert prompt.mode == mode


def test_version_comes_from_the_template_file():
    assert load_prompt("correction").version == "1"


def test_hash_is_twelve_hex_chars_of_sha256_of_the_resolved_text():
    prompt = load_prompt("correction")
    assert len(prompt.hash) == 12
    assert prompt.hash == hashlib.sha256(prompt.text.encode("utf-8")).hexdigest()[:12]


def test_hash_differs_between_modes():
    assert load_prompt("correction").hash != load_prompt("translation").hash


def test_hash_is_stable_across_calls():
    assert load_prompt("correction").hash == load_prompt("correction").hash


def test_editing_the_voice_body_changes_the_hash(tmp_path):
    # This is the whole point of storing a hash next to a hand-bumped version.
    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe terse.\n", encoding="utf-8")
    (tmp_path / "correction.md").write_text(
        "---\nversion: 1\n---\nFix errors.\n\n{{VOICE}}\n", encoding="utf-8"
    )
    first = load_prompt("correction", prompts_dir=tmp_path)

    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe very terse.\n", encoding="utf-8")
    second = load_prompt("correction", prompts_dir=tmp_path)

    assert first.version == second.version == "1"
    assert first.hash != second.hash


def test_missing_placeholder_is_an_error(tmp_path):
    (tmp_path / "voice.md").write_text("---\nversion: 1\n---\nBe terse.\n", encoding="utf-8")
    (tmp_path / "correction.md").write_text("---\nversion: 1\n---\nFix errors.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="\\{\\{VOICE\\}\\}"):
        load_prompt("correction", prompts_dir=tmp_path)


def test_correction_prompt_forbids_introducing_banned_punctuation():
    text = load_prompt("correction").text
    assert "Never introduce an em dash or a semicolon" in text


def test_translation_prompt_forbids_adding_information():
    assert "Add nothing that is not there." in load_prompt("translation").text
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `uv run pytest tests/test_prompts.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.core.prompts'`

- [ ] **Step 6: Write `src/slackchat/core/prompts.py`**

```python
"""Prompt loading, {{VOICE}} resolution, versioning and hashing.

Two identifiers travel with every run: a version you bump by hand, and a hash
of the resolved text. The hash catches the case the version cannot — editing a
prompt file and forgetting to bump. Without it, every cross-version eval
comparison could quietly be a lie.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from slackchat.core.types import Mode

VOICE_PLACEHOLDER = "{{VOICE}}"
HASH_LENGTH = 12

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    mode: Mode
    version: str
    text: str
    hash: str


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` block into flat ``key: value`` pairs and a body.

    Deliberately not YAML: the frontmatter is one scalar, and adding a parser
    dependency for it would be worse than this regex.
    """
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw.strip()
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, raw[match.end():].strip()


def load_prompt(mode: Mode, prompts_dir: Path | None = None) -> Prompt:
    """Load the template for ``mode``, inline ``voice.md``, hash the result."""
    directory = prompts_dir if prompts_dir is not None else _PROMPTS_DIR

    voice_meta, voice_body = parse_frontmatter(
        (directory / "voice.md").read_text(encoding="utf-8")
    )
    del voice_meta  # informational only; the hash covers the body
    template_path = directory / f"{mode}.md"
    template_meta, template_body = parse_frontmatter(
        template_path.read_text(encoding="utf-8")
    )

    if VOICE_PLACEHOLDER not in template_body:
        raise ValueError(f"{template_path} is missing the {VOICE_PLACEHOLDER} placeholder")

    resolved = template_body.replace(VOICE_PLACEHOLDER, voice_body)
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:HASH_LENGTH]
    return Prompt(
        mode=mode,
        version=template_meta.get("version", "0"),
        text=resolved,
        hash=digest,
    )
```

- [ ] **Step 7: Make the wheel carry the markdown and SQL data files**

Append to `pyproject.toml`:

```toml
[tool.uv.build-backend]
source-include = ["src/slackchat/prompts/*.md", "src/slackchat/store/*.sql", "src/slackchat/eval/*.md", "src/slackchat/eval/cases/*.yaml"]
```

Run: `uv sync && uv run python -c "from slackchat.core.prompts import load_prompt; p=load_prompt('correction'); print(p.version, p.hash, len(p.text))"`
Expected: prints `1 <12 hex chars> <a few thousand>`

- [ ] **Step 8: Run the test to verify it passes**

Run: `uv run pytest tests/test_prompts.py -q`
Expected: PASS, 12 tests.

- [ ] **Step 9: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add pyproject.toml src/slackchat/prompts src/slackchat/core/prompts.py tests/test_prompts.py
git commit -m "feat: add versioned prompts with voice constraint and resolved-text hashing"
```

---

### Task 6: Provider protocol, Anthropic provider, pricing table

**Files:**
- Create: `src/slackchat/providers/base.py`
- Create: `src/slackchat/providers/pricing.py`
- Create: `src/slackchat/providers/anthropic.py`
- Test: `tests/test_pricing.py`
- Test: `tests/test_anthropic_provider.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (`providers/` may not import `core/`).
- Produces:
  - `slackchat.providers.base.Completion(text: str, input_tokens: int | None, output_tokens: int | None, model: str)` — frozen
  - `slackchat.providers.base.ProviderError(RuntimeError)`
  - `slackchat.providers.base.Provider` — Protocol with `name: str` and `complete(self, system: str, user: str, *, model: str) -> Completion`
  - `slackchat.providers.pricing.PRICES_USD_PER_MTOK: dict[str, tuple[float, float]]`
  - `slackchat.providers.pricing.normalise_model_id(model: str) -> str`
  - `slackchat.providers.pricing.cost_usd(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None`
  - `slackchat.providers.anthropic.AnthropicProvider(client=None, max_tokens: int = 4096)` with `name = "anthropic"`

Note the module name collision: `slackchat/providers/anthropic.py` shadows the installed `anthropic` package for absolute imports inside that file unless `from __future__ import annotations` plus an explicit `import anthropic` at module level is used — Python 3 uses absolute imports by default, so `import anthropic` inside `slackchat/providers/anthropic.py` resolves to the *installed SDK*, not itself. That is correct and intended; the test in step 5 proves it.

- [ ] **Step 1: Write the failing pricing test**

```python
from slackchat.providers.pricing import (
    PRICES_USD_PER_MTOK,
    cost_usd,
    normalise_model_id,
)


def test_haiku_is_in_the_table_at_one_and_five():
    assert PRICES_USD_PER_MTOK["claude-haiku-4-5"] == (1.00, 5.00)


def test_undated_id_resolves():
    assert normalise_model_id("claude-haiku-4-5") == "claude-haiku-4-5"


def test_dated_id_normalises_to_the_undated_key():
    # Defensive: if the API ever echoes a dated id, cost must still be right.
    assert normalise_model_id("claude-haiku-4-5-20251001") == "claude-haiku-4-5"


def test_a_trailing_non_date_suffix_is_left_alone():
    assert normalise_model_id("claude-haiku-4-5-preview") == "claude-haiku-4-5-preview"


def test_cost_of_a_known_model():
    # 1000 input at $1/MTok + 400 output at $5/MTok
    assert cost_usd("claude-haiku-4-5", 1000, 400) == 0.003


def test_cost_of_a_dated_known_model():
    assert cost_usd("claude-haiku-4-5-20251001", 1000, 400) == 0.003


def test_unknown_model_is_none_never_zero():
    assert cost_usd("some-local-llama", 1000, 400) is None


def test_missing_token_counts_are_none_never_zero():
    assert cost_usd("claude-haiku-4-5", None, 400) is None
    assert cost_usd("claude-haiku-4-5", 1000, None) is None


def test_zero_tokens_is_a_real_zero():
    assert cost_usd("claude-haiku-4-5", 0, 0) == 0.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_pricing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.providers.pricing'`

- [ ] **Step 3: Write `src/slackchat/providers/base.py` and `pricing.py`**

`src/slackchat/providers/base.py`:

```python
"""The provider seam. ``core/`` depends on this module and nothing else here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(RuntimeError):
    """Any provider-side failure, with the SDK exception as ``__cause__``.

    Providers wrap their SDK's exceptions in this so that ``core/`` can catch
    a failure without importing a vendor SDK.
    """


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    model: str


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, model: str) -> Completion: ...
```

`src/slackchat/providers/pricing.py`:

```python
"""Prices are data, not logic, so that a price change is a one-line edit.

Keys are the model ids the API returns in ``response.model``. As of
2026-08-23 that is the undated ``claude-haiku-4-5``; ``normalise_model_id``
strips a trailing date anyway, so a dated echo still costs correctly.
"""

from __future__ import annotations

import re

# model id -> (USD per 1M input tokens, USD per 1M output tokens)
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
}

_DATE_SUFFIX_RE = re.compile(r"-\d{8}\Z")
_PER_MILLION = 1_000_000


def normalise_model_id(model: str) -> str:
    return _DATE_SUFFIX_RE.sub("", model)


def cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Cost in USD, or ``None`` when it cannot be known.

    ``None`` rather than ``0.0`` on purpose: a zero here would be a lie
    inside the very data used to evaluate the tool.
    """
    if input_tokens is None or output_tokens is None:
        return None
    prices = PRICES_USD_PER_MTOK.get(normalise_model_id(model))
    if prices is None:
        return None
    in_price, out_price = prices
    total = (input_tokens * in_price + output_tokens * out_price) / _PER_MILLION
    return round(total, 8)
```

- [ ] **Step 4: Run the pricing test to verify it passes**

Run: `uv run pytest tests/test_pricing.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Write the failing provider test**

No network: a stub client object stands in for `anthropic.Anthropic()`.

```python
import types

import pytest

from slackchat.providers.anthropic import AnthropicProvider
from slackchat.providers.base import Completion, ProviderError


class _StubMessages:
    def __init__(self, response, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class _StubClient:
    def __init__(self, response=None, error=None):
        self.messages = _StubMessages(response, error)


def _response(blocks, model="claude-haiku-4-5", in_tokens=42, out_tokens=17):
    return types.SimpleNamespace(
        content=blocks,
        model=model,
        usage=types.SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
    )


def _text_block(text):
    return types.SimpleNamespace(type="text", text=text)


def test_the_installed_sdk_is_importable_from_the_shadowing_module():
    # slackchat/providers/anthropic.py must resolve `import anthropic` to the
    # installed SDK, not to itself.
    from slackchat.providers import anthropic as module

    assert module.anthropic.__name__ == "anthropic"


def test_complete_returns_a_completion():
    client = _StubClient(_response([_text_block("I finished the task yesterday.")]))
    provider = AnthropicProvider(client=client)
    result = provider.complete("SYSTEM", "USER", model="claude-haiku-4-5")
    assert result == Completion(
        text="I finished the task yesterday.",
        input_tokens=42,
        output_tokens=17,
        model="claude-haiku-4-5",
    )


def test_name_is_anthropic():
    assert AnthropicProvider(client=_StubClient(_response([]))).name == "anthropic"


def test_request_shape_matches_haiku_requirements():
    client = _StubClient(_response([_text_block("ok")]))
    AnthropicProvider(client=client, max_tokens=1234).complete(
        "SYSTEM", "USER", model="claude-haiku-4-5"
    )
    (kwargs,) = client.messages.calls
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["max_tokens"] == 1234
    assert kwargs["system"] == "SYSTEM"
    assert kwargs["messages"] == [{"role": "user", "content": "USER"}]
    # Haiku 4.5 rejects effort and takes no thinking parameter.
    assert "thinking" not in kwargs
    assert "output_config" not in kwargs


def test_multiple_text_blocks_are_concatenated():
    client = _StubClient(_response([_text_block("one "), _text_block("two")]))
    result = AnthropicProvider(client=client).complete("s", "u", model="m")
    assert result.text == "one two"


def test_non_text_blocks_are_ignored():
    blocks = [types.SimpleNamespace(type="thinking", thinking="hmm"), _text_block("out")]
    result = AnthropicProvider(client=_StubClient(_response(blocks))).complete(
        "s", "u", model="m"
    )
    assert result.text == "out"


def test_model_comes_from_the_response_not_the_request():
    client = _StubClient(_response([_text_block("ok")], model="claude-haiku-4-5-20251001"))
    result = AnthropicProvider(client=client).complete("s", "u", model="claude-haiku-4-5")
    assert result.model == "claude-haiku-4-5-20251001"


def test_sdk_errors_become_provider_errors():
    client = _StubClient(None, error=RuntimeError("connection reset"))
    with pytest.raises(ProviderError) as excinfo:
        AnthropicProvider(client=client).complete("s", "u", model="m")
    assert "connection reset" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/test_anthropic_provider.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.providers.anthropic'`

- [ ] **Step 7: Write `src/slackchat/providers/anthropic.py`**

```python
"""Anthropic provider. The only module in the project that talks to the API."""

from __future__ import annotations

import anthropic

from slackchat.providers.base import Completion, ProviderError

DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    """Calls the Messages API once and returns plain text plus token counts.

    ``max_tokens`` is generous relative to the task (a chat message in, a chat
    message out) and small enough to stay well inside the SDK's non-streaming
    timeout. No ``thinking`` and no ``output_config.effort``: Haiku 4.5 takes
    neither, and ``effort`` is rejected outright.
    """

    name = "anthropic"

    def __init__(self, client: object | None = None, max_tokens: int = DEFAULT_MAX_TOKENS):
        # Zero-arg construction resolves ANTHROPIC_API_KEY, then any other
        # configured credential source, from the environment.
        self._client = client if client is not None else anthropic.Anthropic()
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, model: str) -> Completion:
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # wrapped so core/ never sees an SDK type
            raise ProviderError(str(exc)) from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            model=getattr(response, "model", model),
        )
```

- [ ] **Step 8: Run the provider test to verify it passes**

Run: `uv run pytest tests/test_anthropic_provider.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 9: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/providers tests/test_pricing.py tests/test_anthropic_provider.py
git commit -m "feat: add provider protocol, Anthropic provider and pricing table"
```

---

### Task 7: The core pipeline

`process()` is the single code path. Everything after this task is a caller.

**Files:**
- Create: `src/slackchat/core/pipeline.py`
- Create: `tests/conftest.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `core.types`, `core.detect.detect`, `core.diffing.diff_words`, `core.prompts.load_prompt`, `core.validate.*`, `providers.base.{Provider, Completion, ProviderError}`
- Produces:
  - `slackchat.core.pipeline.process(text, mode=None, *, provider, limits, model, prompt=None, cost_fn=None, clock=None, id_factory=None, timer=None) -> Result`
  - `tests/conftest.py`: `FakeProvider` (queue of replies, records calls), `make_result(**overrides) -> Result`, fixture `fake_provider`, fixture `limits`, fixture `isolated_paths` (points `SLACKCHAT_CONFIG` and `SLACKCHAT_DB` at `tmp_path`), fixture `sample_result`

`make_result` lives in `conftest.py` rather than in whichever test file needed it first, so that later test modules never import from a sibling test module — that only works by accident of `sys.path` and breaks the moment `tests/` gains an `__init__.py`.

Injection rationale: `process()` cannot import `providers.pricing` (contract 2 forbids it) and must not read the clock or generate ids unpredictably in tests. `cost_fn`, `clock`, `id_factory` and `timer` all default to real implementations, so ordinary callers pass only the first four arguments.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import os

import pytest

from slackchat.core.types import Limits, Result
from slackchat.providers.base import Completion, ProviderError


def make_result(**overrides) -> Result:
    """A fully populated Result for tests that need a row, not a run."""
    base = dict(
        run_id="run0001",
        original="I has finish",
        output="I finished",
        mode="correction",
        forced=False,
        changes=[],
        changed_ratio=0.5,
        flags=["retried"],
        provider="anthropic",
        model="claude-haiku-4-5",
        prompt_version="1",
        prompt_hash="abcdef012345",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.0002,
        latency_ms=250,
        created_at="2026-08-23T10:00:00Z",
        error=None,
    )
    base.update(overrides)
    return Result(**base)


@pytest.fixture
def sample_result():
    return make_result


class FakeProvider:
    """Returns queued replies in order. Records every call it received."""

    name = "fake"

    def __init__(self, replies, *, error=None, model="claude-haiku-4-5"):
        if isinstance(replies, str):
            replies = [replies]
        self._replies = list(replies)
        self._error = error
        self._model = model
        self.calls = []

    def complete(self, system, user, *, model):
        self.calls.append({"system": system, "user": user, "model": model})
        if self._error is not None:
            raise ProviderError(self._error)
        if not self._replies:
            raise AssertionError("FakeProvider ran out of queued replies")
        text = self._replies.pop(0)
        return Completion(
            text=text,
            input_tokens=100,
            output_tokens=20,
            model=self._model,
        )


@pytest.fixture
def fake_provider():
    return FakeProvider


@pytest.fixture
def limits():
    return Limits(max_changed_ratio=0.25, max_length_ratio=1.5, max_retries=1)


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Keep every test off the real ~/.config and ~/.local/share."""
    monkeypatch.setenv("SLACKCHAT_CONFIG", str(tmp_path / "config" / "config.toml"))
    monkeypatch.setenv("SLACKCHAT_DB", str(tmp_path / "data" / "runs.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(var, raising=False)
    os.makedirs(tmp_path / "config", exist_ok=True)
    return tmp_path
```

- [ ] **Step 2: Write the failing pipeline test**

```python
import pytest

from slackchat.core.pipeline import process
from slackchat.core.prompts import Prompt
from slackchat.core.types import EmptyInputError
from slackchat.core.validate import (
    FLAG_BANNED_CHAR,
    FLAG_EMPTY_OUTPUT,
    FLAG_MECHANICAL,
    FLAG_OVER_EDIT,
    FLAG_RETRIED,
    FLAG_UNKNOWN_PRICING,
)

PROMPT = Prompt(mode="correction", version="7", text="SYSTEM PROMPT", hash="abcdef012345")


def run(provider, text, limits, **kwargs):
    kwargs.setdefault("prompt", PROMPT)
    kwargs.setdefault("model", "claude-haiku-4-5")
    kwargs.setdefault("clock", lambda: "2026-08-23T10:00:00Z")
    kwargs.setdefault("id_factory", lambda: "run0001")
    kwargs.setdefault("timer", iter([0.0, 0.25, 0.25, 0.60]).__next__)
    return process(text, kwargs.pop("mode", None), provider=provider, limits=limits, **kwargs)


# --- happy paths ------------------------------------------------------------

def test_correction_of_a_real_error(fake_provider, limits):
    provider = fake_provider("I finished the task yesterday.")
    result = run(provider, "I has finish the task yesterday.", limits)
    assert result.output == "I finished the task yesterday."
    assert result.mode == "correction"
    assert result.forced is False
    assert result.flags == []
    assert result.changed_ratio == 0.3333
    assert result.run_id == "run0001"
    assert result.created_at == "2026-08-23T10:00:00Z"
    assert result.latency_ms == 250
    assert result.prompt_version == "7"
    assert result.prompt_hash == "abcdef012345"
    assert result.provider == "fake"
    assert result.model == "claude-haiku-4-5"
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert result.cost_usd == pytest.approx(0.0002)
    assert result.error is None


def test_already_correct_text_comes_back_untouched(fake_provider, limits):
    text = "The deployment failed because the config was missing."
    result = run(fake_provider(text), text, limits)
    assert result.output == text
    assert result.changed_ratio == 0.0
    assert [c.kind for c in result.changes] == ["equal"]
    assert result.flags == []


def test_vietnamese_input_routes_to_translation(fake_provider, limits):
    provider = fake_provider("I finished the task yesterday.")
    result = run(provider, "Tôi đã hoàn thành task hôm qua.", limits)
    assert result.mode == "translation"
    assert result.forced is False


def test_explicit_mode_sets_forced_and_overrides_detection(fake_provider, limits):
    provider = fake_provider("I am done.")
    result = run(provider, "Tôi đã xong.", limits, mode="correction")
    assert result.mode == "correction"
    assert result.forced is True


def test_the_user_message_is_the_input_text(fake_provider, limits):
    provider = fake_provider("ok")
    run(provider, "some input", limits)
    assert provider.calls[0]["user"] == "some input"
    assert provider.calls[0]["system"] == "SYSTEM PROMPT"


# --- empty input ------------------------------------------------------------

@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_input_is_rejected_before_any_api_call(fake_provider, limits, text):
    provider = fake_provider(["should never be used"])
    with pytest.raises(EmptyInputError):
        run(provider, text, limits)
    assert provider.calls == []


# --- sanitize ---------------------------------------------------------------

def test_emoji_are_stripped_from_the_output(fake_provider, limits):
    provider = fake_provider("Looks good 👍")
    result = run(provider, "Looks good", limits)
    assert result.output == "Looks good"
    assert result.flags == []


# --- retry ------------------------------------------------------------------

def test_over_edit_triggers_one_retry_and_the_retry_wins(fake_provider, limits):
    provider = fake_provider(
        [
            "Unfortunately the deployment was unsuccessful due to a missing configuration file.",
            "The deployment failed because the config was missing.",
        ]
    )
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert len(provider.calls) == 2
    assert result.output == "The deployment failed because the config was missing."
    assert result.flags == [FLAG_RETRIED]
    assert result.latency_ms == 600  # both attempts counted


def test_the_retry_instruction_goes_on_the_user_message(fake_provider, limits):
    provider = fake_provider(
        ["Deploy failed; rollback done.", "Deploy failed. Rollback done."]
    )
    run(provider, "Deploy failed. Rollback done.", limits)
    first, second = provider.calls
    assert first["user"] == "Deploy failed. Rollback done."
    assert second["user"].startswith("Deploy failed. Rollback done.")
    assert "previous attempt was rejected" in second["user"]
    assert "semicolon" in second["user"]
    # The system prompt is untouched, so prompt_hash still identifies the prompt
    assert first["system"] == second["system"] == "SYSTEM PROMPT"


def test_persistent_over_edit_keeps_the_flag_after_the_retry(fake_provider, limits):
    bloated = "Unfortunately the deployment was unsuccessful due to a missing configuration file."
    provider = fake_provider([bloated, bloated])
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert len(provider.calls) == 2
    assert result.flags == [FLAG_OVER_EDIT, FLAG_RETRIED]
    assert result.output == bloated


def test_max_retries_zero_means_one_attempt(fake_provider, limits):
    from dataclasses import replace

    bloated = "Unfortunately the deployment was entirely unsuccessful for many reasons."
    provider = fake_provider([bloated])
    result = run(
        provider,
        "The deployment failed because the config was missing.",
        replace(limits, max_retries=0),
    )
    assert len(provider.calls) == 1
    assert result.flags == [FLAG_OVER_EDIT]
    assert FLAG_RETRIED not in result.flags


# --- mechanical fallback ----------------------------------------------------

def test_persistent_banned_char_falls_back_mechanically(fake_provider, limits):
    provider = fake_provider(
        ["Deploy failed; rollback done.", "Deploy failed; rollback done."]
    )
    result = run(provider, "Deploy failed. Rollback done.", limits)
    assert result.output == "Deploy failed, rollback done."
    assert result.flags == [FLAG_BANNED_CHAR, FLAG_RETRIED, FLAG_MECHANICAL]
    # the diff is recomputed against the substituted text
    assert result.changed_ratio == 0.5


def test_over_edit_alone_never_triggers_mechanical_substitution(fake_provider, limits):
    bloated = "Unfortunately the deployment was entirely unsuccessful for many reasons."
    provider = fake_provider([bloated, bloated])
    result = run(provider, "The deployment failed because the config was missing.", limits)
    assert FLAG_MECHANICAL not in result.flags


# --- empty output -----------------------------------------------------------

def test_empty_output_is_flagged_and_retried(fake_provider, limits):
    provider = fake_provider(["", ""])
    result = run(provider, "Some input here.", limits)
    assert result.flags == [FLAG_EMPTY_OUTPUT, FLAG_RETRIED]
    assert result.output == ""


# --- pricing ----------------------------------------------------------------

def test_unknown_pricing_sets_the_flag_and_a_null_cost(fake_provider, limits):
    provider = fake_provider("ok", model="some-local-llama")
    result = run(provider, "some input", limits)
    assert result.cost_usd is None
    assert result.flags == [FLAG_UNKNOWN_PRICING]


# --- provider failure -------------------------------------------------------

def test_provider_failure_becomes_a_result_with_an_error(fake_provider, limits):
    provider = fake_provider([], error="rate limited")
    result = run(provider, "I has finish the task.", limits)
    assert result.error == "rate limited"
    assert result.output == ""
    assert result.mode == "correction"
    assert result.cost_usd is None
    assert result.input_tokens is None
    assert result.run_id == "run0001"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.core.pipeline'`

- [ ] **Step 4: Write `src/slackchat/core/pipeline.py`**

```python
"""``process()`` — the single entry point of the whole system.

The CLI renders what this returns. The server serialises it. The eval runner
asserts on it. There is deliberately no second code path.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from slackchat.core.detect import detect
from slackchat.core.diffing import diff_words
from slackchat.core.prompts import Prompt, load_prompt
from slackchat.core.types import Change, EmptyInputError, Limits, Mode, Result
from slackchat.core.validate import (
    FLAG_MECHANICAL,
    FLAG_RETRIED,
    FLAG_UNKNOWN_PRICING,
    FLAG_BANNED_CHAR,
    Violation,
    find_violations,
    mechanical_replace,
    retry_suffix,
    sanitize,
)
from slackchat.providers.base import Completion, Provider, ProviderError


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _dedupe(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered = []
    for flag in flags:
        if flag not in seen:
            seen.add(flag)
            ordered.append(flag)
    return ordered


def process(
    text: str,
    mode: Mode | None = None,
    *,
    provider: Provider,
    limits: Limits,
    model: str,
    prompt: Prompt | None = None,
    cost_fn: Callable[[str, int | None, int | None], float | None] | None = None,
    clock: Callable[[], str] | None = None,
    id_factory: Callable[[], str] | None = None,
    timer: Callable[[], float] | None = None,
) -> Result:
    """Detect, prompt, complete, sanitize, diff, validate, retry once, return.

    ``cost_fn`` is injected, never imported: ``core/`` may not reach
    ``providers.pricing`` (contract 2, and ``import-linter`` sees function-level
    imports too, so a lazy import would not dodge it). With no ``cost_fn`` the
    cost is unknown, which is the honest default for a caller that did not
    supply a price table. ``service.py`` always supplies one.
    """
    if not text.strip():
        raise EmptyInputError("input is empty or whitespace only")

    if cost_fn is None:
        def cost_fn(_model, _in_tokens, _out_tokens):  # noqa: ARG001
            return None

    clock = clock or _utc_now
    id_factory = id_factory or _new_id
    timer = timer or time.monotonic

    resolved_mode: Mode = mode if mode is not None else detect(text)
    forced = mode is not None
    active_prompt = prompt if prompt is not None else load_prompt(resolved_mode)

    run_id = id_factory()
    created_at = clock()

    elapsed = 0.0
    attempt = 0
    suffix = ""
    flags: list[str] = []
    completion: Completion | None = None
    output = ""
    changes: list[Change] = []
    changed_ratio = 0.0

    while True:
        started = timer()
        try:
            completion = provider.complete(
                active_prompt.text, text + suffix, model=model
            )
        except ProviderError as exc:
            return Result(
                run_id=run_id,
                original=text,
                output="",
                mode=resolved_mode,
                forced=forced,
                changes=[],
                changed_ratio=0.0,
                flags=_dedupe(flags),
                provider=provider.name,
                model=model,
                prompt_version=active_prompt.version,
                prompt_hash=active_prompt.hash,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=int(round((elapsed + (timer() - started)) * 1000)),
                created_at=created_at,
                error=str(exc),
            )
        elapsed += timer() - started

        output = sanitize(completion.text)
        changes, changed_ratio = diff_words(text, output)
        violations = find_violations(
            original=text,
            output=output,
            mode=resolved_mode,
            changed_ratio=changed_ratio,
            max_changed_ratio=limits.max_changed_ratio,
        )

        if not violations or attempt >= limits.max_retries:
            flags.extend(v.flag for v in violations)
            if attempt > 0:
                flags.append(FLAG_RETRIED)
            output, changes, changed_ratio = _apply_last_resort(
                violations, text, output, changes, changed_ratio, flags
            )
            break

        attempt += 1
        suffix = retry_suffix(violations)

    if cost_fn(completion.model, completion.input_tokens, completion.output_tokens) is None:
        flags.append(FLAG_UNKNOWN_PRICING)
    cost = cost_fn(completion.model, completion.input_tokens, completion.output_tokens)

    return Result(
        run_id=run_id,
        original=text,
        output=output,
        mode=resolved_mode,
        forced=forced,
        changes=changes,
        changed_ratio=changed_ratio,
        flags=_dedupe(flags),
        provider=provider.name,
        model=completion.model,
        prompt_version=active_prompt.version,
        prompt_hash=active_prompt.hash,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        cost_usd=cost,
        latency_ms=int(round(elapsed * 1000)),
        created_at=created_at,
        error=None,
    )


def _apply_last_resort(
    violations: list[Violation],
    original: str,
    output: str,
    changes: list[Change],
    changed_ratio: float,
    flags: list[str],
) -> tuple[str, list[Change], float]:
    """Substitute banned characters mechanically, and only those.

    Over-edit gets no mechanical remedy: there is no safe machine way to undo
    a rewrite, so it is reported as a flag and the output is returned as-is.
    """
    if not any(v.flag == FLAG_BANNED_CHAR for v in violations):
        return output, changes, changed_ratio
    replaced = mechanical_replace(output)
    if replaced == output:
        return output, changes, changed_ratio
    flags.append(FLAG_MECHANICAL)
    new_changes, new_ratio = diff_words(original, replaced)
    return replaced, new_changes, new_ratio
```

- [ ] **Step 5: Add the `cost_fn` wiring to the test helper**

Because `process()` no longer knows the price table, the test's `run()` helper must supply it. Amend the helper written in step 2 to:

```python
def run(provider, text, limits, **kwargs):
    from slackchat.providers.pricing import cost_usd

    kwargs.setdefault("cost_fn", cost_usd)
    kwargs.setdefault("prompt", PROMPT)
    kwargs.setdefault("model", "claude-haiku-4-5")
    kwargs.setdefault("clock", lambda: "2026-08-23T10:00:00Z")
    kwargs.setdefault("id_factory", lambda: "run0001")
    kwargs.setdefault("timer", iter([0.0, 0.25, 0.25, 0.60]).__next__)
    return process(text, kwargs.pop("mode", None), provider=provider, limits=limits, **kwargs)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -q`
Expected: PASS, 19 tests. `FLAG_UNKNOWN_PRICING` is appended *after* the violation flags on purpose; if an ordering assertion fails, fix the test's expectation only when it contradicts that documented ordering, never by reordering the append.

Run: `uv run lint-imports`
Expected: `Contracts: 3 kept, 0 broken.`

- [ ] **Step 7: Commit**

```bash
git add src/slackchat/core/pipeline.py tests/conftest.py tests/test_pipeline.py
git commit -m "feat: add core pipeline with sanitize, validate and single retry"
```

---

### Task 8: Service wiring, one-shot CLI, diff rendering

Covers spec slices 2, 3 (except auto-copy, which is Task 9) and 5. `service.py` is introduced here without logging; Task 11 adds the log write to this one place, and every caller inherits it.

**Files:**
- Create: `src/slackchat/service.py`
- Create: `src/slackchat/cli/render.py`
- Create: `src/slackchat/cli/main.py`
- Test: `tests/test_service.py`
- Test: `tests/test_render.py`
- Test: `tests/test_cli_oneshot.py`

**Interfaces:**
- Consumes: `config.load_config`, `core.pipeline.process`, `core.prompts.load_prompt`, `core.detect.detect`, `providers.anthropic.AnthropicProvider`, `providers.pricing.cost_usd`, `core.types.{Result, Mode, EmptyInputError}`
- Produces:
  - `slackchat.service.Service` — `run(text: str, mode: Mode | None = None, *, client: str) -> Result`
  - `slackchat.service.build_service(config: Config | None = None, provider: Provider | None = None) -> Service`
  - `slackchat.service.UnknownProviderError(RuntimeError)`
  - `slackchat.cli.render.render_result(result, *, color: bool) -> str`
  - `slackchat.cli.render.render_inline_diff(changes, *, color: bool) -> str`
  - `slackchat.cli.main.main(argv: list[str] | None = None) -> int`
  - `slackchat.cli.main.EXIT_OK = 0`, `EXIT_EMPTY_INPUT = 1`, `EXIT_USAGE = 2`, `EXIT_PROVIDER_ERROR = 3`
  - `slackchat.cli.main.SUBCOMMANDS: frozenset[str]`

- [ ] **Step 1: Write the failing service test**

```python
import pytest

from slackchat import service as svc
from slackchat.config import Config, ProviderConfig
from slackchat.core.types import EmptyInputError, Limits


def test_build_service_uses_the_injected_provider(isolated_paths, fake_provider):
    provider = fake_provider("out")
    service = svc.build_service(Config(), provider=provider)
    result = service.run("I has finish", client="cli")
    assert result.output == "out"
    assert result.provider == "fake"


def test_the_real_prompt_and_price_table_are_wired_in(isolated_paths, fake_provider):
    provider = fake_provider("The deployment failed.")
    service = svc.build_service(Config(), provider=provider)
    result = service.run("The deployment failed.", client="cli")
    assert result.prompt_version == "1"
    assert len(result.prompt_hash) == 12
    # 100 input + 20 output tokens on Haiku pricing
    assert result.cost_usd == pytest.approx(0.0002)
    assert result.flags == []


def test_limits_come_from_config(isolated_paths, fake_provider):
    tight = Config(limits=Limits(max_changed_ratio=0.0, max_length_ratio=1.5, max_retries=0))
    provider = fake_provider("Totally different sentence entirely.")
    result = svc.build_service(tight, provider=provider).run("Original text here.", client="cli")
    assert "over_edit_suspected" in result.flags
    assert len(provider.calls) == 1


def test_each_mode_gets_its_own_prompt(isolated_paths, fake_provider):
    provider = fake_provider(["a", "b"])
    service = svc.build_service(Config(), provider=provider)
    correction = service.run("I has finish", client="cli")
    translation = service.run("Tôi đã xong", client="cli")
    assert correction.prompt_hash != translation.prompt_hash
    assert translation.mode == "translation"


def test_empty_input_propagates(isolated_paths, fake_provider):
    service = svc.build_service(Config(), provider=fake_provider([]))
    with pytest.raises(EmptyInputError):
        service.run("   ", client="cli")


def test_unknown_provider_name_is_a_clear_error(isolated_paths):
    bad = Config(provider=ProviderConfig(name="openai", model="whatever"))
    with pytest.raises(svc.UnknownProviderError, match="openai"):
        svc.build_service(bad)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.service'`

- [ ] **Step 3: Write `src/slackchat/service.py`**

```python
"""The one wiring layer. CLI, server and eval runner all come through here.

``core/`` knows nothing about config files, price tables or the database.
This module knows about all three and about nothing else, which is what makes
"one shared core service" a property of the code rather than a claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from slackchat.config import Config, load_config
from slackchat.core.pipeline import process
from slackchat.core.prompts import Prompt, load_prompt
from slackchat.core.types import Mode, Result
from slackchat.providers.base import Provider
from slackchat.providers.pricing import cost_usd


class UnknownProviderError(RuntimeError):
    """Raised when config names a provider that does not exist."""


def _build_provider(config: Config) -> Provider:
    if config.provider.name == "anthropic":
        from slackchat.providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    raise UnknownProviderError(
        f"unknown provider {config.provider.name!r}; known providers: anthropic"
    )


@dataclass(frozen=True)
class Service:
    config: Config
    provider: Provider

    def run(self, text: str, mode: Mode | None = None, *, client: str) -> Result:
        """Process ``text`` and return the Result.

        ``client`` records which surface asked (``cli``, ``server``, ``eval``).
        It is unused until Task 11 adds the log write, and it is required now
        so that no caller can be added later without declaring itself.
        """
        del client  # used by the logging added in Task 11
        return process(
            text,
            mode,
            provider=self.provider,
            limits=self.config.limits,
            model=self.config.provider.model,
            prompt=self._prompt_for(text, mode),
            cost_fn=cost_usd,
        )

    def _prompt_for(self, text: str, mode: Mode | None) -> Prompt | None:
        # Let the pipeline detect and load, unless the mode is already known.
        return load_prompt(mode) if mode is not None else None


def build_service(config: Config | None = None, provider: Provider | None = None) -> Service:
    resolved = config if config is not None else load_config()
    return Service(config=resolved, provider=provider or _build_provider(resolved))
```

- [ ] **Step 4: Run the service test to verify it passes**

Run: `uv run pytest tests/test_service.py -q`
Expected: PASS, 6 tests. Then `uv run lint-imports` — expected `3 kept, 0 broken` (`service` is an outer layer, so it may import anything).

- [ ] **Step 5: Write the failing render test**

```python
from slackchat.cli.render import render_inline_diff, render_result
from slackchat.core.types import Change, Result

RED = "\x1b[31m"
GREEN = "\x1b[32m"
RESET = "\x1b[0m"


def _result(**overrides):
    base = dict(
        run_id="run0001",
        original="I has finish the task yesterday.",
        output="I finished the task yesterday.",
        mode="correction",
        forced=False,
        changes=[
            Change("equal", "I", "I"),
            Change("replace", "has finish", "finished"),
            Change("equal", "the task yesterday.", "the task yesterday."),
        ],
        changed_ratio=0.3333,
        flags=[],
        provider="anthropic",
        model="claude-haiku-4-5",
        prompt_version="1",
        prompt_hash="abcdef012345",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.0002,
        latency_ms=250,
        created_at="2026-08-23T10:00:00Z",
        error=None,
    )
    base.update(overrides)
    return Result(**base)


def test_plain_diff_uses_text_markers():
    diff = render_inline_diff(_result().changes, color=False)
    assert diff == "I [-has finish-]{+finished+} the task yesterday."


def test_coloured_diff_wraps_the_changed_words_only():
    diff = render_inline_diff(_result().changes, color=True)
    assert diff.startswith("I ")
    assert f"{RED}has finish{RESET}" in diff
    assert f"{GREEN}finished{RESET}" in diff
    assert "the task yesterday." in diff
    assert RED not in diff.split("finished")[-1]


def test_unchanged_text_renders_no_markers():
    changes = [Change("equal", "All good.", "All good.")]
    assert render_inline_diff(changes, color=False) == "All good."


def test_result_starts_with_the_clean_output():
    rendered = render_result(_result(), color=False)
    assert rendered.splitlines()[0] == "I finished the task yesterday."


def test_meta_line_carries_mode_ratio_model_latency_and_cost():
    rendered = render_result(_result(), color=False)
    assert "correction" in rendered
    assert "33%" in rendered
    assert "claude-haiku-4-5" in rendered
    assert "250ms" in rendered
    assert "$0.000200" in rendered


def test_unknown_cost_renders_as_a_dash_not_a_zero():
    rendered = render_result(_result(cost_usd=None), color=False)
    assert "$0.000000" not in rendered
    assert "cost n/a" in rendered


def test_forced_mode_is_marked():
    assert "forced" in render_result(_result(forced=True), color=False)


def test_flags_are_listed_on_their_own_line():
    rendered = render_result(_result(flags=["over_edit_suspected", "retried"]), color=False)
    assert "flags: over_edit_suspected, retried" in rendered


def test_no_flag_line_when_there_are_no_flags():
    assert "flags:" not in render_result(_result(), color=False)


def test_error_result_renders_the_error_and_no_diff():
    rendered = render_result(
        _result(output="", changes=[], changed_ratio=0.0, error="rate limited"), color=False
    )
    assert "error: rate limited" in rendered
    assert "[-" not in rendered
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/test_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.cli.render'`

- [ ] **Step 7: Write `src/slackchat/cli/render.py`**

```python
"""Terminal rendering. Knows nothing about the pipeline beyond ``Result``."""

from __future__ import annotations

from slackchat.core.types import Change, Result

RESET = "\x1b[0m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
DIM = "\x1b[2m"


def _paint(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def render_inline_diff(changes: list[Change], *, color: bool) -> str:
    """One line showing what moved.

    Without colour the markers are ``[-removed-]`` and ``{+added+}`` so that a
    redirected run is still readable, and so that a screenshot in a bug report
    survives losing its escape codes.
    """
    parts: list[str] = []
    for change in changes:
        if change.kind == "equal":
            parts.append(change.before)
            continue
        if change.before:
            parts.append(
                _paint(change.before, RED, color) if color else f"[-{change.before}-]"
            )
        if change.after:
            parts.append(
                _paint(change.after, GREEN, color) if color else f"{{+{change.after}+}}"
            )
    return " ".join(p for p in parts if p)


def _meta_line(result: Result) -> str:
    cost = f"${result.cost_usd:.6f}" if result.cost_usd is not None else "cost n/a"
    mode = f"{result.mode} (forced)" if result.forced else result.mode
    return " · ".join(
        [
            mode,
            f"changed {round(result.changed_ratio * 100)}%",
            result.model,
            f"{result.latency_ms}ms",
            cost,
        ]
    )


def render_result(result: Result, *, color: bool) -> str:
    """The human view: clean output, then how it got there."""
    lines = [result.output, ""]
    if result.error:
        lines.append(_paint(f"error: {result.error}", RED, color))
        return "\n".join(lines).rstrip() + "\n"

    lines.append(_paint(f"  {_meta_line(result)}", DIM, color))
    lines.append(f"  {render_inline_diff(result.changes, color=color)}")
    if result.flags:
        lines.append(_paint(f"  flags: {', '.join(result.flags)}", RED, color))
    return "\n".join(lines) + "\n"
```

- [ ] **Step 8: Run the render test to verify it passes**

Run: `uv run pytest tests/test_render.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 9: Write the failing CLI test**

```python
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
    wire("I finished the task yesterday.")
    code = cli.main(["I has finish the task yesterday."])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert out.splitlines()[0] == "I finished the task yesterday."
    assert "[-has finish-]" in out
    assert "correction" in out


def test_raw_prints_only_the_output_text(wire, capsys):
    wire("I finished the task yesterday.")
    code = cli.main(["--raw", "I has finish the task yesterday."])
    assert code == cli.EXIT_OK
    assert capsys.readouterr().out == "I finished the task yesterday.\n"


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
    provider = wire("I finished the task yesterday.")
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
    # "detect the bug" is one argv entry, so it is text, not the subcommand.
    wire("Detect the bug in staging.")
    assert cli.main(["detect the bug in staging"]) == cli.EXIT_OK
    assert "Detect the bug in staging." in capsys.readouterr().out
```

- [ ] **Step 10: Run it to verify it fails**

Run: `uv run pytest tests/test_cli_oneshot.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.cli.main'`

- [ ] **Step 11: Write `src/slackchat/cli/main.py`**

Subcommands are dispatched by inspecting `argv[0]` rather than with `argparse` subparsers, because `slackchat "some text"` and `slackchat detect "some text"` have to coexist: a bare positional and a subparser cannot both own the first slot in `argparse`.

```python
"""CLI entry point. Dispatch, exit codes, and nothing else of substance."""

from __future__ import annotations

import argparse
import sys

from slackchat.cli.render import render_result
from slackchat.core.detect import detect
from slackchat.core.types import EmptyInputError
from slackchat.service import build_service

EXIT_OK = 0
EXIT_EMPTY_INPUT = 1
EXIT_USAGE = 2
EXIT_PROVIDER_ERROR = 3

SUBCOMMANDS = frozenset({"detect", "log", "eval", "serve"})


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _read_stdin() -> str:
    return sys.stdin.read()


def _oneshot_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slackchat",
        description="Fix English text, or translate Vietnamese to English.",
    )
    parser.add_argument("text", nargs="?", help="text to process; omit to read stdin or start a session")
    parser.add_argument(
        "--mode",
        choices=["correction", "translation"],
        default=None,
        help="force a mode instead of detecting it",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="print the processed text only, with no diff or metadata",
    )
    return parser


def _run_oneshot(text: str, *, mode: str | None, raw: bool) -> int:
    service = build_service()
    try:
        result = service.run(text, mode, client="cli")
    except EmptyInputError:
        print("slackchat: input is empty", file=sys.stderr)
        return EXIT_EMPTY_INPUT

    if raw:
        print(result.output)
    else:
        print(render_result(result, color=_stdout_is_tty()), end="")

    if result.error:
        print(f"slackchat: {result.error}", file=sys.stderr)
        return EXIT_PROVIDER_ERROR
    return EXIT_OK


def _cmd_detect(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat detect")
    parser.add_argument("text")
    args = parser.parse_args(argv)
    print(detect(args.text))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in SUBCOMMANDS:
        command, rest = args[0], args[1:]
        if command == "detect":
            return _cmd_detect(rest)
        print(f"slackchat: '{command}' is not implemented yet", file=sys.stderr)
        return EXIT_USAGE

    parsed = _oneshot_parser().parse_args(args)

    if parsed.text is not None:
        return _run_oneshot(parsed.text, mode=parsed.mode, raw=parsed.raw)

    if not _stdin_is_tty():
        return _run_oneshot(_read_stdin().strip("\n"), mode=parsed.mode, raw=parsed.raw)

    print("slackchat: interactive session arrives in a later task", file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

`argparse` already exits with status 2 on a bad `--mode`, which is why `EXIT_USAGE` is 2.

- [ ] **Step 12: Run the CLI test to verify it passes**

Run: `uv run pytest tests/test_cli_oneshot.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 13: Manual verification with a real key**

```bash
export ANTHROPIC_API_KEY=...   # or rely on an existing credential source
uv run slackchat "I has finish the task yesterday."
uv run slackchat "The deployment failed because the config was missing."
uv run slackchat "Tôi đã hoàn thành task hôm qua."
uv run slackchat detect "Cà phê ở đây ngon."
uv run slackchat --raw "I has finish the task yesterday." | pbcopy
uv run slackchat "I has finish" > /tmp/out.txt && cat /tmp/out.txt
```

Expected, in order: a minimal correction with a coloured diff; the second sentence returned **unchanged** with `changed 0%`; a natural English translation; `translation`; clean text on the clipboard; the redirected file containing plain markers with no escape codes.

Read the second one carefully. If an already-correct sentence comes back reworded, the number one constraint is not being met and the correct response is to tighten `prompts/correction.md` and bump its `version`, not to raise `max_changed_ratio`.

- [ ] **Step 14: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/service.py src/slackchat/cli tests/test_service.py tests/test_render.py tests/test_cli_oneshot.py
git commit -m "feat: add service wiring, one-shot CLI, detect subcommand and diff rendering"
```

---

### Task 9: Clipboard auto-copy

Spec §10.3. Small, but it has its own rule (tty-gated, no flag) and its own failure mode (polluting piped output), so it gets its own test cycle.

**Files:**
- Create: `src/slackchat/cli/clipboard.py`
- Modify: `src/slackchat/cli/main.py` (`_run_oneshot`)
- Test: `tests/test_clipboard.py`

**Interfaces:**
- Consumes: `slackchat.config.CliConfig`
- Produces:
  - `slackchat.cli.clipboard.copy(text: str) -> bool` — returns whether the copy succeeded
  - `slackchat.cli.clipboard.PBCOPY = "pbcopy"`

- [ ] **Step 1: Write the failing test**

```python
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
    copied = wired("I finished the task yesterday.")
    cli.main(["I has finish the task yesterday."])
    assert copied == ["I finished the task yesterday."]
    assert "(copied to clipboard)" in capsys.readouterr().out


def test_the_copied_text_never_contains_escape_codes(wired, capsys):
    copied = wired("I finished the task yesterday.")
    cli.main(["I has finish the task yesterday."])
    assert "\x1b" not in copied[0]


def test_piped_stdout_copies_nothing_and_says_nothing(wired, capsys):
    copied = wired("I finished the task yesterday.", stdout_tty=False)
    cli.main(["I has finish the task yesterday."])
    assert copied == []
    assert "copied" not in capsys.readouterr().out


def test_auto_copy_off_copies_nothing(wired, capsys):
    copied = wired("I finished the task yesterday.", auto_copy=False)
    cli.main(["I has finish the task yesterday."])
    assert copied == []
    assert "copied" not in capsys.readouterr().out


def test_raw_on_a_tty_still_copies(wired, capsys):
    copied = wired("I finished the task yesterday.")
    cli.main(["--raw", "I has finish the task yesterday."])
    assert copied == ["I finished the task yesterday."]


def test_an_errored_result_is_not_copied(wired, capsys, monkeypatch, isolated_paths, fake_provider):
    from slackchat import service as svc

    provider = fake_provider([], error="rate limited")
    monkeypatch.setattr(cli, "build_service", lambda *a, **k: svc.build_service(Config(), provider=provider))
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)
    copied = []
    monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: copied.append(text) or True)
    cli.main(["I has finish"])
    assert copied == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_clipboard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.cli.clipboard'`

- [ ] **Step 3: Write `src/slackchat/cli/clipboard.py`**

```python
"""Clipboard access. A CLI concern only; ``core/`` knows nothing about it."""

from __future__ import annotations

import subprocess

PBCOPY = "pbcopy"


def copy(text: str) -> bool:
    """Put ``text`` on the macOS clipboard. Never raises.

    A missing or failing ``pbcopy`` is a convenience that did not happen, not
    an error worth failing the run over. macOS-only is accepted for Phase 1.
    """
    try:
        subprocess.run([PBCOPY], input=text.encode("utf-8"), check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
```

- [ ] **Step 4: Wire it into `_run_oneshot`**

Add the import near the top of `src/slackchat/cli/main.py`:

```python
from slackchat.cli.clipboard import copy as copy_to_clipboard
```

Replace the body of `_run_oneshot` after the render block with:

```python
    if raw:
        print(result.output)
    else:
        print(render_result(result, color=_stdout_is_tty()), end="")

    if result.error:
        print(f"slackchat: {result.error}", file=sys.stderr)
        return EXIT_PROVIDER_ERROR

    if _stdout_is_tty() and service.config.cli.auto_copy and result.output:
        if copy_to_clipboard(result.output):
            print("(copied to clipboard)")
    return EXIT_OK
```

The module-level alias `copy_to_clipboard` is what the test patches, which is why the import is aliased rather than used as `clipboard.copy`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_clipboard.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 6: Manual verification**

```bash
uv run slackchat "I has finish the task yesterday."   # expect "(copied to clipboard)", then paste it somewhere
uv run slackchat "I has finish" > /tmp/out.txt        # expect no "copied" line in the file
pbpaste
```

- [ ] **Step 7: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/cli/clipboard.py src/slackchat/cli/main.py tests/test_clipboard.py
git commit -m "feat: auto-copy output to clipboard when stdout is a tty"
```

---

### Task 10: REPL session and banner

Covers spec slice 4 and §10.1–10.2. Verifiable without an API key for everything except the model call itself.

**Files:**
- Create: `src/slackchat/cli/banner.py`
- Create: `src/slackchat/cli/repl.py`
- Modify: `src/slackchat/cli/main.py` (`main`, to enter the REPL instead of erroring)
- Test: `tests/test_banner.py`
- Test: `tests/test_repl.py`

**Interfaces:**
- Consumes: `slackchat.service.Service`, `slackchat.cli.render.render_result`, `slackchat.cli.clipboard.copy`
- Produces:
  - `slackchat.cli.banner.GLYPHS: dict[str, tuple[str, ...]]`
  - `slackchat.cli.banner.GLYPH_HEIGHT = 5`, `GLYPH_WIDTH = 3`
  - `slackchat.cli.banner.render_word(word: str) -> str`
  - `slackchat.cli.banner.WORDMARK = "SLACKCHAT"`
  - `slackchat.cli.banner.HINT = "Ctrl+D or /exit to quit"`
  - `slackchat.cli.banner.banner(color: bool) -> str`
  - `slackchat.cli.repl.PROMPT = "> "`, `CONTINUATION = "... "`, `EXIT_WORDS = frozenset({"/exit", "/quit"})`
  - `slackchat.cli.repl.run_session(service, *, read_line, write, color: bool, copy_fn) -> int`

- [ ] **Step 1: Write the failing banner test**

```python
from slackchat.cli.banner import (
    GLYPH_HEIGHT,
    GLYPH_WIDTH,
    GLYPHS,
    HINT,
    WORDMARK,
    banner,
    render_word,
)


def test_every_wordmark_letter_has_a_glyph():
    assert set(WORDMARK) <= set(GLYPHS)


def test_every_glyph_is_rectangular():
    for letter, rows in GLYPHS.items():
        assert len(rows) == GLYPH_HEIGHT, letter
        assert {len(r) for r in rows} == {GLYPH_WIDTH}, letter


def test_render_word_of_a_single_letter_is_that_glyph():
    assert render_word("T") == "\n".join(GLYPHS["T"])


def test_render_word_joins_letters_with_one_space_column():
    rendered = render_word("TT").splitlines()
    assert len(rendered) == GLYPH_HEIGHT
    assert rendered[0] == GLYPHS["T"][0] + " " + GLYPHS["T"][0]


def test_wordmark_lines_are_all_the_same_width():
    lines = render_word(WORDMARK).splitlines()
    assert len(lines) == GLYPH_HEIGHT
    expected = len(WORDMARK) * GLYPH_WIDTH + (len(WORDMARK) - 1)
    assert {len(line) for line in lines} == {expected}


def test_render_word_is_case_insensitive():
    assert render_word("slackchat") == render_word("SLACKCHAT")


def test_banner_includes_the_hint():
    assert HINT in banner(color=False)
    assert "Ctrl+D" in HINT


def test_banner_without_colour_has_no_escape_codes():
    assert "\x1b" not in banner(color=False)


def test_banner_with_colour_dims_the_hint():
    assert "\x1b[2m" in banner(color=True)


def test_banner_adds_no_dependency():
    import slackchat.cli.banner as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "import " in source  # sanity: the file parses as a module
    for forbidden in ("pyfiglet", "art", "rich"):
        assert forbidden not in source
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_banner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.cli.banner'`

- [ ] **Step 3: Write `src/slackchat/cli/banner.py`**

```python
"""A hardcoded 3x5 block font. No dependency, no runtime figlet."""

from __future__ import annotations

GLYPH_HEIGHT = 5
GLYPH_WIDTH = 3

B = "█"  # FULL BLOCK

GLYPHS: dict[str, tuple[str, ...]] = {
    "A": (f"{B}{B}{B}", f"{B} {B}", f"{B}{B}{B}", f"{B} {B}", f"{B} {B}"),
    "C": (f"{B}{B}{B}", f"{B}  ", f"{B}  ", f"{B}  ", f"{B}{B}{B}"),
    "H": (f"{B} {B}", f"{B} {B}", f"{B}{B}{B}", f"{B} {B}", f"{B} {B}"),
    "K": (f"{B} {B}", f"{B} {B}", f"{B}{B} ", f"{B} {B}", f"{B} {B}"),
    "L": (f"{B}  ", f"{B}  ", f"{B}  ", f"{B}  ", f"{B}{B}{B}"),
    "S": (f"{B}{B}{B}", f"{B}  ", f"{B}{B}{B}", f"  {B}", f"{B}{B}{B}"),
    "T": (f"{B}{B}{B}", f" {B} ", f" {B} ", f" {B} ", f" {B} "),
}

WORDMARK = "SLACKCHAT"
HINT = "Ctrl+D or /exit to quit"

DIM = "\x1b[2m"
RESET = "\x1b[0m"


def render_word(word: str) -> str:
    """Lay the glyphs side by side, one blank column between letters."""
    letters = [GLYPHS[ch] for ch in word.upper()]
    return "\n".join(
        " ".join(letter[row] for letter in letters) for row in range(GLYPH_HEIGHT)
    )


def banner(color: bool) -> str:
    hint = f"{DIM}{HINT}{RESET}" if color else HINT
    return f"{render_word(WORDMARK)}\n\n{hint}\n"
```

- [ ] **Step 4: Run the banner test to verify it passes, then look at it**

Run: `uv run pytest tests/test_banner.py -q`
Expected: PASS, 10 tests.

Run: `uv run python -c "from slackchat.cli.banner import banner; print(banner(color=False))"`
Expected: a legible `SLACKCHAT` in block letters. If a letter looks wrong, fix the glyph — the rectangularity test will keep you honest about the widths.

- [ ] **Step 5: Write the failing REPL test**

```python
import pytest

from slackchat.cli import repl
from slackchat.config import Config


class Reader:
    """Stands in for input(). Raises EOFError when the script runs out."""

    def __init__(self, lines):
        self._lines = list(lines)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


@pytest.fixture
def session(isolated_paths, fake_provider):
    def _session(lines, replies, *, copy_fn=None):
        from slackchat import service as svc

        provider = fake_provider(replies)
        service = svc.build_service(Config(), provider=provider)
        reader = Reader(lines)
        written = []
        code = repl.run_session(
            service,
            read_line=reader,
            write=written.append,
            color=False,
            copy_fn=copy_fn or (lambda _text: False),
        )
        return code, provider, reader, "".join(written)

    return _session


def test_banner_is_printed_once_at_the_start(session):
    _, _, _, out = session([], [])
    assert out.count("Ctrl+D or /exit to quit") == 1


def test_a_single_line_turn_is_submitted_on_the_blank_line(session):
    code, provider, reader, out = session(
        ["I has finish the task yesterday.", ""], ["I finished the task yesterday."]
    )
    assert code == 0
    assert len(provider.calls) == 1
    assert provider.calls[0]["user"] == "I has finish the task yesterday."
    assert "I finished the task yesterday." in out


def test_prompts_switch_to_the_continuation_form_after_the_first_line(session):
    _, _, reader, _ = session(["one", "two", ""], ["out"])
    assert reader.prompts[:3] == [repl.PROMPT, repl.CONTINUATION, repl.CONTINUATION]


def test_a_multi_line_paste_is_one_input_joined_by_newlines(session):
    _, provider, _, _ = session(["line one", "line two", "line three", ""], ["out"])
    assert len(provider.calls) == 1
    assert provider.calls[0]["user"] == "line one\nline two\nline three"


def test_two_turns_are_two_runs(session):
    _, provider, _, _ = session(["first", "", "second", ""], ["a", "b"])
    assert [c["user"] for c in provider.calls] == ["first", "second"]


def test_blank_line_with_an_empty_buffer_is_ignored_silently(session):
    code, provider, reader, out = session(["", "", "real input", ""], ["out"])
    assert len(provider.calls) == 1
    assert "empty" not in out.lower()
    assert "error" not in out.lower()
    # prompt returns to the primary form each time
    assert reader.prompts[:3] == [repl.PROMPT, repl.PROMPT, repl.PROMPT]


@pytest.mark.parametrize("word", ["/exit", "/quit"])
def test_exit_words_leave_immediately(session, word):
    code, provider, _, _ = session([word, "never reached", ""], ["out"])
    assert code == 0
    assert provider.calls == []


def test_exit_word_mid_input_discards_the_buffer_and_leaves(session):
    code, provider, _, _ = session(["half a thought", "/exit"], ["out"])
    assert code == 0
    assert provider.calls == []


def test_exit_word_is_matched_after_stripping_whitespace(session):
    code, provider, _, _ = session(["  /exit  "], ["out"])
    assert code == 0
    assert provider.calls == []


def test_eof_leaves_immediately(session):
    code, provider, _, _ = session([], ["out"])
    assert code == 0
    assert provider.calls == []


def test_ctrl_c_leaves_immediately(isolated_paths, fake_provider):
    from slackchat import service as svc

    def reader(_prompt):
        raise KeyboardInterrupt

    service = svc.build_service(Config(), provider=fake_provider([]))
    written = []
    assert (
        repl.run_session(
            service, read_line=reader, write=written.append, color=False, copy_fn=lambda _t: False
        )
        == 0
    )


def test_each_turn_copies_when_the_copy_function_succeeds(session):
    copied = []
    _, _, _, out = session(
        ["a b c", "", "d e f", ""], ["a b c", "d e f"], copy_fn=lambda t: copied.append(t) or True
    )
    assert copied == ["a b c", "d e f"]
    assert out.count("(copied to clipboard)") == 2


def test_a_provider_error_is_shown_and_the_session_continues(isolated_paths, fake_provider):
    from slackchat import service as svc

    provider = fake_provider([], error="rate limited")
    service = svc.build_service(Config(), provider=provider)
    reader = Reader(["something", "", "another", ""])
    written = []
    code = repl.run_session(
        service, read_line=reader, write=written.append, color=False, copy_fn=lambda _t: False
    )
    out = "".join(written)
    assert code == 0
    assert out.count("rate limited") == 2  # the session did not abort on the first
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run pytest tests/test_repl.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.cli.repl'`

- [ ] **Step 7: Write `src/slackchat/cli/repl.py`**

```python
"""The interactive session. A blank line submits; ``/exit`` leaves at once."""

from __future__ import annotations

from collections.abc import Callable

from slackchat.cli.banner import banner
from slackchat.cli.render import render_result
from slackchat.core.types import EmptyInputError
from slackchat.service import Service

PROMPT = "> "
CONTINUATION = "... "
EXIT_WORDS = frozenset({"/exit", "/quit"})


def run_session(
    service: Service,
    *,
    read_line: Callable[[str], str],
    write: Callable[[str], None],
    color: bool,
    copy_fn: Callable[[str], bool],
) -> int:
    """Read multi-line turns until EOF, Ctrl+C, or an exit word.

    A blank line submits the buffer, which is what lets a multi-line paste
    arrive as one input instead of being chopped into a run per line.
    """
    write(banner(color))
    buffer: list[str] = []

    while True:
        prompt = CONTINUATION if buffer else PROMPT
        try:
            line = read_line(prompt)
        except (EOFError, KeyboardInterrupt):
            write("\n")
            return 0

        if line.strip() in EXIT_WORDS:
            return 0

        if line.strip() == "" and not buffer:
            continue  # nothing typed yet: silently re-prompt

        if line.strip() != "" or not buffer:
            buffer.append(line)
            continue

        text = "\n".join(buffer)
        buffer = []
        _handle_turn(service, text, write=write, color=color, copy_fn=copy_fn)


def _handle_turn(
    service: Service,
    text: str,
    *,
    write: Callable[[str], None],
    color: bool,
    copy_fn: Callable[[str], bool],
) -> None:
    try:
        result = service.run(text, client="cli")
    except EmptyInputError:
        return

    write(render_result(result, color=color))
    if result.error:
        return
    if service.config.cli.auto_copy and result.output and copy_fn(result.output):
        write("(copied to clipboard)\n")
```

- [ ] **Step 8: Wire the REPL into `main`**

In `src/slackchat/cli/main.py`, add:

```python
from slackchat.cli.clipboard import copy as copy_to_clipboard
from slackchat.cli.repl import run_session
```

and replace the final block of `main`:

```python
    service = build_service()
    return run_session(
        service,
        read_line=input,
        write=lambda chunk: print(chunk, end=""),
        color=_stdout_is_tty(),
        copy_fn=copy_to_clipboard if _stdout_is_tty() else (lambda _text: False),
    )
```

- [ ] **Step 9: Run the REPL test to verify it passes**

Run: `uv run pytest tests/test_repl.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 10: Manual verification**

```bash
uv run slackchat
```

Check each of these in one sitting:
- the banner and the dim hint appear once
- `> ` becomes `... ` on the second line of a turn
- a blank line submits, and the diff appears
- pasting a three-line block and pressing Enter twice produces **one** result, not three
- pressing Enter on an empty prompt does nothing at all
- typing half a sentence and then `/exit` leaves immediately
- Ctrl+D leaves

Then confirm the pipe path is unaffected: `printf 'I has finish\n' | uv run slackchat` returns one result and does not enter the session.

- [ ] **Step 11: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/cli/banner.py src/slackchat/cli/repl.py src/slackchat/cli/main.py tests/test_banner.py tests/test_repl.py
git commit -m "feat: add multi-line REPL session with hardcoded banner"
```

---

### Task 11: SQLite logging and the log command

Covers spec slice 7 and §7. The `runs` and `reviews` tables are exactly as specified; `eval_results` is the one addition, justified at the top of this plan.

**Files:**
- Create: `src/slackchat/store/schema.sql`
- Create: `src/slackchat/store/sqlite.py`
- Modify: `src/slackchat/service.py` (log after `process()` returns)
- Modify: `src/slackchat/cli/main.py` (`log` subcommand)
- Test: `tests/test_store.py`
- Test: `tests/test_cli_log.py`

**Interfaces:**
- Consumes: `slackchat.core.types.Result`, `slackchat.config.db_path`
- Produces:
  - `slackchat.store.sqlite.connect(path: Path | None = None) -> sqlite3.Connection`
  - `slackchat.store.sqlite.insert_run(conn, result: Result, client: str) -> None`
  - `slackchat.store.sqlite.recent_runs(conn, limit: int = 20, mode: str | None = None) -> list[sqlite3.Row]`
  - `slackchat.store.sqlite.insert_review(conn, *, run_id, dimension, score, reviewer, note, created_at) -> None`
  - `slackchat.store.sqlite.insert_eval_result(conn, *, run_id, case_id, check_name, passed) -> None`
  - `slackchat.store.sqlite.pass_rate(conn, prompt_version: str) -> tuple[int, int]`
  - `slackchat.store.sqlite.prompt_hash_conflicts(conn) -> list[tuple[str, int]]`

- [ ] **Step 1: Write `src/slackchat/store/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS runs (
  run_id         TEXT PRIMARY KEY,
  created_at     TEXT NOT NULL,        -- ISO8601 UTC
  client         TEXT NOT NULL,        -- cli | server | eval
  mode           TEXT NOT NULL,        -- correction | translation
  forced         INTEGER NOT NULL,
  input          TEXT NOT NULL,
  output         TEXT NOT NULL,
  provider       TEXT NOT NULL,
  model          TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  prompt_hash    TEXT NOT NULL,
  input_tokens   INTEGER,
  output_tokens  INTEGER,
  cost_usd       REAL,
  latency_ms     INTEGER,
  changed_ratio  REAL,
  flags          TEXT,                 -- JSON array
  error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_mode_version ON runs(mode, prompt_version);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);

CREATE TABLE IF NOT EXISTS reviews (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  dimension  TEXT NOT NULL,
  score      INTEGER NOT NULL CHECK (score IN (0,1,2)),
  reviewer   TEXT NOT NULL,            -- 'human' or a model id
  note       TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, dimension, reviewer)
);

-- Not in the design spec. Added because pass rate is not derivable from
-- `runs` alone, and spec section 8.1 requires `--compare A B` to be a query.
CREATE TABLE IF NOT EXISTS eval_results (
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  case_id    TEXT NOT NULL,
  check_name TEXT NOT NULL,
  passed     INTEGER NOT NULL,
  PRIMARY KEY (run_id, check_name)
);

CREATE INDEX IF NOT EXISTS idx_eval_results_case ON eval_results(case_id);
```

- [ ] **Step 2: Write the failing store test**

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.store.sqlite'`

- [ ] **Step 4: Write `src/slackchat/store/sqlite.py`**

```python
"""SQLite log. Queryable with SQL, which is what replay eval will need."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from slackchat.core.types import Result

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the run log with WAL enabled.

    WAL is what lets the daemon and the CLI write at the same time without
    one of them getting ``database is locked``.
    """
    if path is None:
        from slackchat.config import db_path  # local import: config is a sibling layer

        path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def insert_run(conn: sqlite3.Connection, result: Result, client: str) -> None:
    conn.execute(
        """
        INSERT INTO runs (
          run_id, created_at, client, mode, forced, input, output, provider,
          model, prompt_version, prompt_hash, input_tokens, output_tokens,
          cost_usd, latency_ms, changed_ratio, flags, error
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            result.run_id,
            result.created_at,
            client,
            result.mode,
            int(result.forced),
            result.original,
            result.output,
            result.provider,
            result.model,
            result.prompt_version,
            result.prompt_hash,
            result.input_tokens,
            result.output_tokens,
            result.cost_usd,
            result.latency_ms,
            result.changed_ratio,
            json.dumps(result.flags),
            result.error,
        ),
    )
    conn.commit()


def recent_runs(
    conn: sqlite3.Connection, limit: int = 20, mode: str | None = None
) -> list[sqlite3.Row]:
    if mode is None:
        sql = "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params: tuple = (limit,)
    else:
        sql = "SELECT * FROM runs WHERE mode = ? ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params = (mode, limit)
    return list(conn.execute(sql, params))


def insert_review(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    dimension: str,
    score: int,
    reviewer: str,
    note: str | None,
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO reviews (run_id, dimension, score, reviewer, note, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (run_id, dimension, score, reviewer, note, created_at),
    )
    conn.commit()


def insert_eval_result(
    conn: sqlite3.Connection, *, run_id: str, case_id: str, check_name: str, passed: bool
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO eval_results (run_id, case_id, check_name, passed)
        VALUES (?,?,?,?)
        """,
        (run_id, case_id, check_name, int(passed)),
    )
    conn.commit()


def pass_rate(conn: sqlite3.Connection, prompt_version: str) -> tuple[int, int]:
    """(cases fully passing, cases run) for one prompt version.

    A case counts as passing only when every one of its checks passed, which
    is the only definition that keeps the ``unchanged`` group meaningful.
    """
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN failures = 0 THEN 1 ELSE 0 END) AS passed,
          COUNT(*) AS total
        FROM (
          SELECT r.run_id, SUM(CASE WHEN e.passed = 0 THEN 1 ELSE 0 END) AS failures
          FROM runs r
          JOIN eval_results e ON e.run_id = r.run_id
          WHERE r.client = 'eval' AND r.prompt_version = ?
          GROUP BY r.run_id
        )
        """,
        (prompt_version,),
    ).fetchone()
    return (row["passed"] or 0, row["total"] or 0)


def prompt_hash_conflicts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Versions logged against more than one resolved-prompt hash.

    A non-empty result means at least one cross-version comparison is a lie.
    """
    rows = conn.execute(
        """
        SELECT prompt_version, COUNT(DISTINCT prompt_hash) AS hashes
        FROM runs
        GROUP BY prompt_version
        HAVING hashes > 1
        ORDER BY prompt_version
        """
    )
    return [(r["prompt_version"], r["hashes"]) for r in rows]
```

- [ ] **Step 5: Run the store test to verify it passes**

Run: `uv run pytest tests/test_store.py -q`
Expected: PASS, 13 tests.

Run: `uv run lint-imports`
Expected: `3 kept, 0 broken` — `store` importing `config` is an outer-to-outer import and no contract covers it.

- [ ] **Step 6: Write the failing service-logging and `log` command test**

`tests/test_cli_log.py`:

```python
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
    conn = logged(["I has finish"], ["I finished"])
    row = conn.execute("SELECT client, mode, input, output FROM runs").fetchone()
    assert row["client"] == "cli"
    assert row["input"] == "I has finish"
    assert row["output"] == "I finished"


def test_the_client_column_separates_eval_from_real_use(logged):
    conn = logged(["I has finish"], ["I finished"], client="eval")
    assert conn.execute("SELECT client FROM runs").fetchone()[0] == "eval"


def test_changed_ratio_is_stored_so_trends_need_no_rediff(logged):
    conn = logged(["I has finish the task yesterday."], ["I finished the task yesterday."])
    assert conn.execute("SELECT changed_ratio FROM runs").fetchone()[0] == 0.3333


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
    logged(["first input", "second input"], ["first output", "second output"])
    assert cli.main(["log", "--last", "1"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "second input" in out
    assert "first input" not in out


def test_log_command_filters_by_mode(logged, capsys):
    logged(["I has finish", "Tôi đã xong"], ["I finished", "I am done"])
    assert cli.main(["log", "--mode", "translation"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Tôi đã xong" in out
    assert "I has finish" not in out


def test_log_command_on_an_empty_database_says_so(isolated_paths, capsys):
    assert cli.main(["log"]) == cli.EXIT_OK
    assert "no runs" in capsys.readouterr().out.lower()
```

- [ ] **Step 7: Run it to verify it fails**

Run: `uv run pytest tests/test_cli_log.py -q`
Expected: FAIL — the assertions about logged rows fail, because `Service.run` still discards `client`.

- [ ] **Step 8: Add the log write to `service.py`**

Replace the `run` method body:

```python
    def run(self, text: str, mode: Mode | None = None, *, client: str) -> Result:
        """Process ``text``, log the outcome, return the Result.

        Logging lives here and nowhere else: ``core/`` must not know about a
        database, and duplicating the write per caller is how a caller ends up
        silently unlogged.
        """
        result = process(
            text,
            mode,
            provider=self.provider,
            limits=self.config.limits,
            model=self.config.provider.model,
            prompt=self._prompt_for(text, mode),
            cost_fn=cost_usd,
        )
        conn = store.connect()
        try:
            store.insert_run(conn, result, client=client)
        finally:
            conn.close()
        return result
```

and add `from slackchat.store import sqlite as store` to the imports.

An `EmptyInputError` propagates out of `process()` before the log write, which is exactly the spec's "no row, no cost, non-zero exit".

- [ ] **Step 9: Add the `log` subcommand to `cli/main.py`**

```python
def _cmd_log(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat log")
    parser.add_argument("--last", type=int, default=20)
    parser.add_argument("--mode", choices=["correction", "translation"], default=None)
    args = parser.parse_args(argv)

    conn = store.connect()
    try:
        rows = store.recent_runs(conn, limit=args.last, mode=args.mode)
    finally:
        conn.close()

    if not rows:
        print("no runs logged yet")
        return EXIT_OK

    for row in rows:
        flags = ",".join(json.loads(row["flags"] or "[]")) or "-"
        cost = f"${row['cost_usd']:.6f}" if row["cost_usd"] is not None else "n/a"
        print(
            f"{row['created_at']}  {row['client']:<6} {row['mode']:<11} "
            f"{row['changed_ratio']:>6.2f}  {cost:>10}  {flags}"
        )
        print(f"    in : {_one_line(row['input'])}")
        print(f"    out: {_one_line(row['output'])}")
    return EXIT_OK


def _one_line(text: str, width: int = 100) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= width else collapsed[: width - 1] + "…"
```

Add `import json` and `from slackchat.store import sqlite as store` to the imports, and route it in `main`:

```python
        if command == "log":
            return _cmd_log(rest)
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `uv run pytest tests/test_cli_log.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 11: Manual verification**

```bash
uv run slackchat "I has finish the task yesterday."
uv run slackchat "Tôi đã hoàn thành task hôm qua."
uv run slackchat "The deployment failed because the config was missing."
uv run slackchat log --last 3
sqlite3 "${XDG_DATA_HOME:-$HOME/.local/share}/slackchat/runs.db" \
  "SELECT created_at, client, mode, changed_ratio, cost_usd, flags FROM runs ORDER BY created_at DESC LIMIT 3;"
```

Expected: three rows, `client` all `cli`, one `translation`, the already-correct sentence at `changed_ratio` 0.0, and real (non-zero, non-null) costs.

- [ ] **Step 12: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/store src/slackchat/service.py src/slackchat/cli/main.py tests/test_store.py tests/test_cli_log.py
git commit -m "feat: log every run to SQLite and add the log command"
```

---

### Task 12: Eval assertions, case files, runner and compare

Covers spec slice 8 and §8.1. The `unchanged` group is the project's primary metric — treat a regression there as a release blocker, never as a case to loosen.

**Files:**
- Create: `src/slackchat/eval/assertions.py`
- Create: `src/slackchat/eval/cases/correction.yaml`
- Create: `src/slackchat/eval/cases/translation.yaml`
- Create: `src/slackchat/eval/runner.py`
- Modify: `src/slackchat/cli/main.py` (`eval` subcommand)
- Test: `tests/test_eval_assertions.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `core.types.{Limits, Result}`, `core.diffing.word_count`, `core.validate.{_EMOJI_RE via a public helper, banned_chars_introduced}`, `service.Service`, `store.sqlite`
- Produces:
  - `slackchat.core.validate.has_emoji(text: str) -> bool` (new public helper added to `validate.py`, so `eval/` does not reach a private regex)
  - `slackchat.eval.assertions.Case(id: str, mode: Mode, input: str, asserts: dict)` — frozen
  - `slackchat.eval.assertions.CheckOutcome(name: str, passed: bool, detail: str)` — frozen
  - `slackchat.eval.assertions.load_cases(directory: Path | None = None) -> list[Case]`
  - `slackchat.eval.assertions.check(case: Case, result: Result, limits: Limits) -> list[CheckOutcome]`
  - `slackchat.eval.assertions.KNOWN_ASSERTIONS: frozenset[str]`
  - `slackchat.eval.runner.run_suite(service, *, cases=None, out=print) -> RunSummary`
  - `slackchat.eval.runner.RunSummary(passed: int, total: int, cost_usd: float, unknown_cost_runs: int, prompt_version: str)` — frozen
  - `slackchat.eval.runner.compare(version_a: str, version_b: str, *, out=print) -> int`

- [ ] **Step 1: Add `has_emoji` to `core/validate.py`**

```python
def has_emoji(text: str) -> bool:
    """True if any emoji survives in ``text``. Used by the eval assertions."""
    return _EMOJI_RE.search(text) is not None
```

- [ ] **Step 2: Write the case files**

`src/slackchat/eval/cases/correction.yaml`. The `unchanged` block comes first because it is the metric that matters most; every sentence in it is already grammatical.

```yaml
- id: noop-001
  mode: correction
  input: "The deployment failed because the config was missing."
  assert: { unchanged: true }

- id: noop-002
  mode: correction
  input: "Hi a @Kenny Trinh is there any progress on this so far?"
  assert: { unchanged: true }

- id: noop-003
  mode: correction
  input: "I have interview at 3:00 but please consider me as optional, thanks"
  assert: { unchanged: true }

- id: noop-004
  mode: correction
  input: "I'm afraid the Oracle here is the whole ERM which is bigger than the Oracle DB that Terry supports as DBA."
  assert: { unchanged: true }

- id: noop-005
  mode: correction
  input: "FYI we're forming a team to research how to register an account to get certified under CodeLink CPN."
  assert: { unchanged: true }

- id: noop-006
  mode: correction
  input: "For now, if we don't prioritise this, we can just announce the info so anyone in the company interested in getting Claude certs can consider it."
  assert: { unchanged: true }

- id: noop-007
  mode: correction
  input: "What's the cost to invite members? Is it free except for the fee to get the certs?"
  assert: { unchanged: true }

- id: noop-008
  mode: correction
  input: "In terms of scope, I guess around 1-2 hours. But of course, Truong can estimate better if needed."
  assert: { unchanged: true }

- id: noop-009
  mode: correction
  input: "3 services they mentioned seem larger and different in type compared to Copilot. We can reach out to Kieu Anh for further context if needed."
  assert: { unchanged: true }

- id: noop-010
  mode: correction
  input: "It costs 30 dollars — that is more than I expected."
  assert:
    unchanged: true
  # The writer's own em dash. Removing it would itself be an over-edit.

- id: fix-001
  mode: correction
  input: "I has finish the task yesterday."
  assert:
    output_contains_any: ["I finished", "I have finished"]
    max_changed_ratio: 0.4

- id: fix-002
  mode: correction
  input: "She's using her personal Claude, it's not suitable for ISO program."
  assert:
    output_contains_any: ["the ISO program"]
    max_changed_ratio: 0.35

- id: fix-003
  mode: correction
  input: "Is it okey to add more a?"
  assert:
    output_contains_any: ["okay"]
    output_excludes: ["okey"]
    max_changed_ratio: 0.5

- id: fix-004
  mode: correction
  input: "Our current developers is using Claude Code plus Novita DeepSeek."
  assert:
    output_contains_any: ["developers are using"]
    max_changed_ratio: 0.3

- id: fix-005
  mode: correction
  input: "I intend to ask Truong help to collect cost for Dental project within July and Aug."
  assert:
    output_contains_any: ["to help", "help to collect the cost", "the cost"]
    max_changed_ratio: 0.45

- id: fix-006
  mode: correction
  input: "It would be nice if we could provide quick update, as Notion may not reflect the current status."
  assert:
    output_contains_any: ["quick updates"]
    max_changed_ratio: 0.3

- id: nobloat-001
  mode: correction
  input: "Any concerns?"
  assert:
    unchanged: true
    max_words: 3

- id: nobloat-002
  mode: correction
  input: "we can just announce the info"
  assert:
    output_excludes: ["I hope", "kindly", "at your earliest convenience", "please do not hesitate"]
    max_changed_ratio: 0.4
```

`src/slackchat/eval/cases/translation.yaml`:

```yaml
- id: tr-001
  mode: translation
  input: "Tôi đã hoàn thành task hôm qua."
  assert:
    output_contains_any: ["finished", "completed"]
    max_words: 12

- id: tr-002
  mode: translation
  input: "Mai họp lúc 3 giờ nhé"
  assert:
    output_contains_any: ["3"]
    max_words: 14

- id: tr-003
  mode: translation
  input: "Anh xem giúp em cái này với, không gấp nên anh cứ từ từ."
  assert:
    output_excludes: ["kindly", "at your earliest convenience", "I hope this message"]
    max_words: 30

- id: tr-004
  mode: translation
  input: "Em định nhờ Trường thu thập chi phí Claude và Novita cho dự án Dental trong tháng 7 và tháng 8. Có vấn đề gì không anh?"
  assert:
    output_contains_any: ["Truong", "Trường"]
    output_excludes: ["moving forward", "circle back"]
    max_words: 55

- id: tr-005
  mode: translation
  input: "Số liệu này chưa khớp, em kiểm tra lại rồi báo anh sau."
  assert:
    output_excludes: ["furthermore", "moreover", "additionally"]
    max_words: 25

- id: tr-006
  mode: translation
  input: "Bên mình đã tham gia CPN rồi, ai muốn thi cert thì ping em nhé."
  assert:
    output_contains_any: ["CPN"]
    max_words: 30
```

- [ ] **Step 3: Write the failing assertions test**

```python
from pathlib import Path

import pytest

from slackchat.core.types import Limits, Result
from slackchat.eval.assertions import (
    KNOWN_ASSERTIONS,
    Case,
    check,
    load_cases,
)

LIMITS = Limits(max_changed_ratio=0.25, max_length_ratio=1.5, max_retries=1)


def _result(original, output, **overrides):
    from slackchat.core.diffing import diff_words

    changes, ratio = diff_words(original, output)
    base = dict(
        run_id="r1",
        original=original,
        output=output,
        mode="correction",
        forced=False,
        changes=changes,
        changed_ratio=ratio,
        flags=[],
        provider="fake",
        model="claude-haiku-4-5",
        prompt_version="1",
        prompt_hash="abcdef012345",
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.0001,
        latency_ms=1,
        created_at="2026-08-23T10:00:00Z",
        error=None,
    )
    base.update(overrides)
    return Result(**base)


def _names(outcomes):
    return {o.name for o in outcomes}


def _failed(outcomes):
    return {o.name for o in outcomes if not o.passed}


# --- universal checks -------------------------------------------------------

def test_the_four_universal_checks_run_without_being_declared():
    case = Case(id="c", mode="correction", input="all good", asserts={})
    outcomes = check(case, _result("all good", "all good"), LIMITS)
    assert _names(outcomes) == {
        "no_emoji",
        "no_banned_char_introduced",
        "non_empty",
        "length_ratio",
    }
    assert _failed(outcomes) == set()


def test_emoji_in_the_output_fails():
    case = Case(id="c", mode="correction", input="all good", asserts={})
    assert "no_emoji" in _failed(check(case, _result("all good", "all good 👍"), LIMITS))


def test_an_introduced_semicolon_fails():
    case = Case(id="c", mode="correction", input="Deploy failed. Rollback done.", asserts={})
    outcomes = check(
        case, _result("Deploy failed. Rollback done.", "Deploy failed; rollback done."), LIMITS
    )
    assert "no_banned_char_introduced" in _failed(outcomes)


def test_the_writers_own_em_dash_does_not_fail_a_correction_case():
    text = "It costs 30 dollars — more than expected."
    case = Case(id="c", mode="correction", input=text, asserts={})
    assert _failed(check(case, _result(text, text), LIMITS)) == set()


def test_an_em_dash_always_fails_a_translation_case():
    case = Case(id="c", mode="translation", input="Tôi xong rồi", asserts={})
    result = _result("Tôi xong rồi", "I am done — finally.", mode="translation")
    assert "no_banned_char_introduced" in _failed(check(case, result, LIMITS))


def test_empty_output_fails():
    case = Case(id="c", mode="correction", input="something", asserts={})
    assert "non_empty" in _failed(check(case, _result("something", ""), LIMITS))


def test_length_ratio_above_the_limit_fails():
    case = Case(id="c", mode="correction", input="one two", asserts={})
    result = _result("one two", "one two three four")  # ratio 2.0 > 1.5
    assert "length_ratio" in _failed(check(case, result, LIMITS))


def test_length_ratio_at_the_limit_passes():
    case = Case(id="c", mode="correction", input="one two", asserts={})
    result = _result("one two", "one two three")  # ratio 1.5
    assert "length_ratio" not in _failed(check(case, result, LIMITS))


# --- declared assertions ----------------------------------------------------

def test_unchanged_passes_on_identical_text():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert _failed(check(case, _result("All good.", "All good."), LIMITS)) == set()


def test_unchanged_ignores_trailing_whitespace_only():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert _failed(check(case, _result("All good.", "All good.  \n"), LIMITS)) == set()


def test_unchanged_is_byte_for_byte_otherwise():
    case = Case(id="c", mode="correction", input="All good.", asserts={"unchanged": True})
    assert "unchanged" in _failed(check(case, _result("All good.", "All  good."), LIMITS))
    assert "unchanged" in _failed(check(case, _result("All good.", "all good."), LIMITS))


def test_output_contains_any_needs_one_match():
    case = Case(
        id="c",
        mode="correction",
        input="I has finish",
        asserts={"output_contains_any": ["I finished", "I have finished"]},
    )
    assert _failed(check(case, _result("I has finish", "I have finished"), LIMITS)) == set()
    assert "output_contains_any" in _failed(
        check(case, _result("I has finish", "I did complete it"), LIMITS)
    )


def test_output_excludes_fails_on_any_hit():
    case = Case(id="c", mode="correction", input="x", asserts={"output_excludes": ["kindly"]})
    assert "output_excludes" in _failed(check(case, _result("x", "Kindly review"), LIMITS))
    assert _failed(check(case, _result("x", "Please review"), LIMITS)) == set()


def test_max_changed_ratio_overrides_the_default_for_one_case():
    case = Case(
        id="c",
        mode="correction",
        input="I has finish the task yesterday.",
        asserts={"max_changed_ratio": 0.4},
    )
    result = _result("I has finish the task yesterday.", "I finished the task yesterday.")
    assert _failed(check(case, result, LIMITS)) == set()  # 0.3333 <= 0.4


def test_max_words_counts_output_words():
    case = Case(id="c", mode="correction", input="Any concerns?", asserts={"max_words": 3})
    assert _failed(check(case, _result("Any concerns?", "Any concerns?"), LIMITS)) == set()
    assert "max_words" in _failed(
        check(case, _result("Any concerns?", "Do you have any concerns at all?"), LIMITS)
    )


def test_an_unknown_assertion_key_is_an_error():
    case = Case(id="c", mode="correction", input="x", asserts={"vibes": "good"})
    with pytest.raises(ValueError, match="vibes"):
        check(case, _result("x", "x"), LIMITS)


def test_known_assertions_is_exactly_the_documented_five():
    assert KNOWN_ASSERTIONS == frozenset(
        {"unchanged", "output_contains_any", "output_excludes", "max_changed_ratio", "max_words"}
    )


# --- loading ----------------------------------------------------------------

def test_the_shipped_cases_load_and_every_key_is_known():
    cases = load_cases()
    assert len(cases) >= 20
    assert {c.mode for c in cases} == {"correction", "translation"}
    for case in cases:
        assert set(case.asserts) <= KNOWN_ASSERTIONS, case.id


def test_case_ids_are_unique():
    ids = [c.id for c in load_cases()]
    assert len(ids) == len(set(ids))


def test_at_least_ten_unchanged_cases_exist():
    unchanged = [c for c in load_cases() if c.asserts.get("unchanged")]
    assert len(unchanged) >= 10


def test_load_cases_from_a_custom_directory(tmp_path):
    (tmp_path / "x.yaml").write_text(
        '- id: a\n  mode: correction\n  input: "hi"\n  assert: { unchanged: true }\n',
        encoding="utf-8",
    )
    cases = load_cases(tmp_path)
    assert [c.id for c in cases] == ["a"]


def test_a_duplicate_id_across_files_is_an_error(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(
            '- id: dup\n  mode: correction\n  input: "hi"\n  assert: {}\n', encoding="utf-8"
        )
    with pytest.raises(ValueError, match="dup"):
        load_cases(tmp_path)
```

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest tests/test_eval_assertions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.eval.assertions'`

- [ ] **Step 5: Write `src/slackchat/eval/assertions.py`**

```python
"""Deterministic assertions. Free, repeatable, and blind to translation quality.

Four checks run on every case without being declared, because they encode the
output constraints that hold for all input. The declared assertions are the
per-case expectations.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from slackchat.core.diffing import word_count
from slackchat.core.types import Limits, Mode, Result
from slackchat.core.validate import banned_chars_introduced, has_emoji

KNOWN_ASSERTIONS = frozenset(
    {"unchanged", "output_contains_any", "output_excludes", "max_changed_ratio", "max_words"}
)

_CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass(frozen=True)
class Case:
    id: str
    mode: Mode
    input: str
    asserts: dict


@dataclass(frozen=True)
class CheckOutcome:
    name: str
    passed: bool
    detail: str


def load_cases(directory: Path | None = None) -> list[Case]:
    """Load every ``*.yaml`` under ``directory``, sorted by filename then order."""
    target = directory if directory is not None else _CASES_DIR
    cases: list[Case] = []
    seen: dict[str, str] = {}
    for path in sorted(target.glob("*.yaml")):
        entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for entry in entries:
            case_id = entry["id"]
            if case_id in seen:
                raise ValueError(
                    f"duplicate case id {case_id!r} in {path.name} and {seen[case_id]}"
                )
            seen[case_id] = path.name
            cases.append(
                Case(
                    id=case_id,
                    mode=entry["mode"],
                    input=entry["input"],
                    asserts=entry.get("assert") or {},
                )
            )
    return cases


def _universal(case: Case, result: Result, limits: Limits) -> list[CheckOutcome]:
    introduced = banned_chars_introduced(case.input, result.output, case.mode)
    in_words = word_count(case.input)
    out_words = word_count(result.output)
    ratio = out_words / in_words if in_words else 0.0
    return [
        CheckOutcome("no_emoji", not has_emoji(result.output), "emoji in output"),
        CheckOutcome(
            "no_banned_char_introduced",
            not introduced,
            f"introduced {' and '.join(introduced)}" if introduced else "",
        ),
        CheckOutcome("non_empty", bool(result.output.strip()), "output is empty"),
        CheckOutcome(
            "length_ratio",
            ratio <= limits.max_length_ratio,
            f"{out_words}/{in_words} words = {ratio:.2f} > {limits.max_length_ratio}",
        ),
    ]


def _declared(case: Case, result: Result) -> list[CheckOutcome]:
    unknown = set(case.asserts) - KNOWN_ASSERTIONS
    if unknown:
        raise ValueError(
            f"case {case.id}: unknown assertion(s) {sorted(unknown)}; "
            f"known: {sorted(KNOWN_ASSERTIONS)}"
        )

    outcomes: list[CheckOutcome] = []
    for name, expected in case.asserts.items():
        if name == "unchanged" and expected:
            # Trailing whitespace is stripped, the rest is byte-for-byte.
            passed = result.output.rstrip() == case.input.rstrip()
            outcomes.append(
                CheckOutcome("unchanged", passed, "" if passed else f"got {result.output!r}")
            )
        elif name == "output_contains_any":
            needles: Iterable[str] = expected
            passed = any(n in result.output for n in needles)
            outcomes.append(
                CheckOutcome(
                    "output_contains_any", passed, "" if passed else f"none of {list(needles)}"
                )
            )
        elif name == "output_excludes":
            hits = [n for n in expected if n.lower() in result.output.lower()]
            outcomes.append(
                CheckOutcome("output_excludes", not hits, f"found {hits}" if hits else "")
            )
        elif name == "max_changed_ratio":
            passed = result.changed_ratio <= float(expected)
            outcomes.append(
                CheckOutcome(
                    "max_changed_ratio",
                    passed,
                    "" if passed else f"{result.changed_ratio} > {expected}",
                )
            )
        elif name == "max_words":
            words = word_count(result.output)
            passed = words <= int(expected)
            outcomes.append(
                CheckOutcome("max_words", passed, "" if passed else f"{words} > {expected}")
            )
    return outcomes


def check(case: Case, result: Result, limits: Limits) -> list[CheckOutcome]:
    """Every outcome for one case, universal checks first.

    A case-level ``max_changed_ratio`` applies to its own declared check only.
    The universal ``length_ratio`` check always uses the configured limit,
    because it guards a different thing (output ballooning) from a different
    direction (words, not tokens changed).
    """
    return _universal(case, result, limits) + _declared(case, result)
```

- [ ] **Step 6: Run the assertions test to verify it passes**

Run: `uv run pytest tests/test_eval_assertions.py -q`
Expected: PASS, 22 tests.

- [ ] **Step 7: Write the failing runner test**

```python
import pytest

from slackchat import service as svc
from slackchat.cli import main as cli
from slackchat.config import Config
from slackchat.eval import runner
from slackchat.eval.assertions import Case
from slackchat.store import sqlite as store

CASES = [
    Case(id="noop-x", mode="correction", input="All good.", asserts={"unchanged": True}),
    Case(
        id="fix-x",
        mode="correction",
        input="I has finish the task yesterday.",
        asserts={"output_contains_any": ["I finished"], "max_changed_ratio": 0.4},
    ),
]


def _service(replies, isolated_paths, fake_provider, config=None):
    return svc.build_service(config or Config(), provider=fake_provider(replies))


def test_all_green_reports_full_pass_rate(isolated_paths, fake_provider):
    service = _service(["All good.", "I finished the task yesterday."], isolated_paths, fake_provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert (summary.passed, summary.total) == (2, 2)
    text = "\n".join(lines)
    assert "2/2" in text


def test_a_failure_is_named_with_the_check_and_the_reason(isolated_paths, fake_provider):
    service = _service(
        ["All good, I think.", "I finished the task yesterday."], isolated_paths, fake_provider
    )
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert (summary.passed, summary.total) == (1, 2)
    text = "\n".join(lines)
    assert "noop-x" in text
    assert "unchanged" in text


def test_total_cost_is_printed_and_real(isolated_paths, fake_provider):
    service = _service(["All good.", "I finished the task yesterday."], isolated_paths, fake_provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    # 2 runs x (100 input + 20 output) on Haiku pricing
    assert summary.cost_usd == pytest.approx(0.0004)
    assert "$0.0004" in "\n".join(lines)


def test_unknown_cost_runs_are_counted_not_treated_as_zero(isolated_paths, fake_provider):
    provider = fake_provider(["All good.", "I finished the task yesterday."], model="local-llama")
    service = svc.build_service(Config(), provider=provider)
    lines = []
    summary = runner.run_suite(service, cases=CASES, out=lines.append)
    assert summary.unknown_cost_runs == 2
    assert "2 run(s) with unknown pricing" in "\n".join(lines)


def test_runs_are_logged_as_eval_not_cli(isolated_paths, fake_provider):
    service = _service(["All good.", "I finished the task yesterday."], isolated_paths, fake_provider)
    runner.run_suite(service, cases=CASES, out=lambda _l: None)
    conn = store.connect()
    assert {r["client"] for r in conn.execute("SELECT client FROM runs")} == {"eval"}


def test_every_check_outcome_is_persisted(isolated_paths, fake_provider):
    service = _service(["All good.", "I finished the task yesterday."], isolated_paths, fake_provider)
    runner.run_suite(service, cases=CASES, out=lambda _l: None)
    conn = store.connect()
    rows = list(conn.execute("SELECT case_id, check_name, passed FROM eval_results"))
    assert {r["case_id"] for r in rows} == {"noop-x", "fix-x"}
    assert all(r["passed"] == 1 for r in rows)


def test_pass_rate_is_derivable_from_sql_afterwards(isolated_paths, fake_provider):
    service = _service(
        ["All good, I think.", "I finished the task yesterday."], isolated_paths, fake_provider
    )
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
```

- [ ] **Step 8: Run it to verify it fails**

Run: `uv run pytest tests/test_eval_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.eval.runner'`

- [ ] **Step 9: Write `src/slackchat/eval/runner.py`**

```python
"""Run the case suite, persist the outcomes, and compare prompt versions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from slackchat.eval.assertions import Case, check, load_cases
from slackchat.service import Service
from slackchat.store import sqlite as store

Out = Callable[[str], None]


@dataclass(frozen=True)
class RunSummary:
    passed: int
    total: int
    cost_usd: float
    unknown_cost_runs: int
    prompt_version: str


def run_suite(service: Service, *, cases: list[Case] | None = None, out: Out = print) -> RunSummary:
    """Run every case, record each check, and print a per-failure report."""
    suite = cases if cases is not None else load_cases()
    conn = store.connect()
    passed_cases = 0
    cost_total = 0.0
    unknown_cost = 0
    prompt_version = "?"
    try:
        for case in suite:
            result = service.run(case.input, case.mode, client="eval")
            prompt_version = result.prompt_version
            if result.cost_usd is None:
                unknown_cost += 1
            else:
                cost_total += result.cost_usd

            outcomes = check(case, result, service.config.limits)
            for outcome in outcomes:
                store.insert_eval_result(
                    conn,
                    run_id=result.run_id,
                    case_id=case.id,
                    check_name=outcome.name,
                    passed=outcome.passed,
                )
            failures = [o for o in outcomes if not o.passed]
            if failures:
                out(f"FAIL {case.id} ({case.mode})")
                out(f"     in : {case.input}")
                out(f"     out: {result.output}")
                for failure in failures:
                    out(f"     - {failure.name}: {failure.detail}")
                if result.flags:
                    out(f"     flags: {', '.join(result.flags)}")
            else:
                passed_cases += 1
    finally:
        conn.close()

    out("")
    out(f"pass rate {passed_cases}/{len(suite)} (prompt_version {prompt_version})")
    out(f"cost ${cost_total:.4f}")
    if unknown_cost:
        out(f"{unknown_cost} run(s) with unknown pricing, excluded from the total")
    return RunSummary(
        passed=passed_cases,
        total=len(suite),
        cost_usd=round(cost_total, 8),
        unknown_cost_runs=unknown_cost,
        prompt_version=prompt_version,
    )


def compare(version_a: str, version_b: str, *, out: Out = print) -> int:
    """Print the recorded pass rate for two prompt versions.

    The hash warning comes first on purpose: comparing two versions whose
    files were edited without a bump produces a number that looks meaningful
    and is not.
    """
    conn = store.connect()
    try:
        for version, hashes in store.prompt_hash_conflicts(conn):
            out(
                f"warning: prompt_version {version} was logged against {hashes} "
                f"different prompt hashes; runs under it are not comparable"
            )
        for version in (version_a, version_b):
            passed, total = store.pass_rate(conn, version)
            rate = f"{passed}/{total}" if total else "no runs"
            pct = f" ({passed / total:.0%})" if total else ""
            out(f"version {version}: {rate}{pct}")
    finally:
        conn.close()
    return 0
```

- [ ] **Step 10: Add the `eval` subcommand to `cli/main.py`**

```python
def _cmd_eval(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat eval")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None)
    args = parser.parse_args(argv)

    if args.compare:
        return eval_compare(args.compare[0], args.compare[1])
    run_suite(build_service())
    return EXIT_OK
```

Imports to add:

```python
from slackchat.eval.runner import compare as eval_compare
from slackchat.eval.runner import run_suite
```

and route it in `main`:

```python
        if command == "eval":
            return _cmd_eval(rest)
```

- [ ] **Step 11: Run the runner test to verify it passes**

Run: `uv run pytest tests/test_eval_runner.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 12: Manual verification with a real key**

```bash
uv run slackchat eval
```

Expected: a per-failure report, then `pass rate N/26` and a real dollar figure of a few tenths of a cent.

Read the failures. Any `FAIL noop-*` on `unchanged` is the number one constraint failing, and the response is to tighten `prompts/correction.md` and bump its `version:` — then:

```bash
uv run slackchat eval
uv run slackchat eval --compare 1 2
```

Expected: the compare line shows both versions' pass rates and no hash warning (because you bumped the version when you edited the file).

- [ ] **Step 13: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/eval src/slackchat/core/validate.py src/slackchat/cli/main.py tests/test_eval_assertions.py tests/test_eval_runner.py
git commit -m "feat: add deterministic eval suite, case files and version compare"
```

---

### Task 13: Rubric with anchors, and human review

Covers spec slice 9 and §8.2–8.3. The anchors are the deliverable, not the dimension names: an unanchored rubric scores the same output two ways on two days and is worth nothing.

**Files:**
- Create: `src/slackchat/eval/rubric.md`
- Create: `src/slackchat/eval/review.py`
- Modify: `src/slackchat/cli/main.py` (`eval --review`)
- Test: `tests/test_rubric.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `core.prompts.parse_frontmatter`, `store.sqlite.{connect, insert_review}`
- Produces:
  - `slackchat.eval.review.DIMENSIONS: dict[str, tuple[str, ...]]` — mode → dimension names
  - `slackchat.eval.review.rubric_version() -> str`
  - `slackchat.eval.review.unreviewed_runs(conn, limit: int, reviewer: str = "human") -> list[sqlite3.Row]`
  - `slackchat.eval.review.review_session(conn, *, limit, read_line, write, clock, reviewer="human") -> int` — returns the number of runs scored

- [ ] **Step 1: Write `src/slackchat/eval/rubric.md`**

Every level has a written anchor and a concrete example. Do not shorten these; the examples are the calibration.

```markdown
---
version: 1
---
# Rubric

Scale: 0, 1, 2. Three levels, because three get scored consistently and five
do not. Score each dimension independently — do not let a good translation
carry a voice failure, or a voice win excuse a dropped fact.

If two levels both seem to fit, take the lower one.

## Translation

### Adequacy — is every idea in the source present, and nothing added?

- **0** — A fact, an ask, a name, a number, or a qualifier is missing, or
  something was invented.
  *Source:* "Em định nhờ Trường thu thập chi phí Claude và Novita cho dự án Dental trong tháng 7 và tháng 8."
  *Output:* "I want Truong to collect the project costs." — drops both
  vendors, the project name, and both months.
- **1** — Everything is present, but one qualifier or hedge shifted in
  strength, or a small detail is blurred.
  *Output:* "I will ask Truong to collect the Claude and Novita costs for the
  Dental project in July and August." — "em định nhờ" is an intention to ask,
  not a decision already taken; "I will ask" is firmer than the source.
- **2** — Every idea is present at the same strength, and nothing is added.
  *Output:* "I intend to ask Truong to collect the Claude and Novita costs for
  the Dental project for July and August."

### Naturalness — does it read as written by a fluent speaker, not translated?

- **0** — Word order, particles, or calques give the translation away.
  *Source:* "Anh xem giúp em cái này với, không gấp nên anh cứ từ từ."
  *Output:* "Brother please see help me this thing, not urgent so brother just
  slowly."
- **1** — Grammatical and understandable, but a native writer would not phrase
  it this way.
  *Output:* "Please help me to take a look at this. It is not urgent so you
  can take your time slowly."
- **2** — Reads like an ordinary work chat message.
  *Output:* "Could you take a look at this? It's not urgent, so no rush."

### Voice compliance — does it match `prompts/voice.md`?

- **0** — Contains something the voice constraint bans outright: an emoji, an
  em dash, a semicolon, or a phrase from the cut list.
  *Output:* "I hope this message finds you well — kindly review the attached
  at your earliest convenience."
- **1** — Nothing banned, but the register drifted formal, or an inflated
  adjective slipped in.
  *Output:* "I would like to request a comprehensive review of this item."
- **2** — Direct, unpadded, hedges kept where the source had them, "Hi a
  @name" preserved when addressing a senior.
  *Output:* "Hi a @Kenny Trinh, any concerns if I ask Truong to look into this?"

### Concision — is it as short as the meaning allows?

- **0** — Noticeably longer than the source with no gain in clarity; one idea
  spread across two sentences.
  *Source:* "Số liệu này chưa khớp, em kiểm tra lại rồi báo anh sau."
  *Output:* "I have noticed that the figures in this document do not appear to
  match up at the present time. I will conduct a further review of them and
  will then provide you with an update afterwards."
- **1** — Slightly padded: a redundant clause, or a filler opener.
  *Output:* "Just to let you know, these numbers don't match yet. I will check
  them again and update you later."
- **2** — No word could be removed without losing meaning.
  *Output:* "These numbers don't match yet. I'll check and update you."

## Correction

Score correction only on cases that *had* an error. A case with no error is
already covered by the `unchanged` assertion, which is binary and does not
need a human.

### Minimality — did it touch only the error?

- **0** — Rewrote correct text: reordered clauses, merged or split sentences,
  swapped in different words, or changed the register.
  *Input:* "Our current developers is using Claude Code plus Novita DeepSeek."
  *Output:* "At present, our development team leverages Claude Code in
  conjunction with Novita DeepSeek."
- **1** — Fixed the error, but also made one unnecessary edit — a synonym, an
  added article, a punctuation change nobody asked for.
  *Output:* "Our current developers are using Claude Code together with Novita
  DeepSeek."
- **2** — Exactly the error changed, nothing else.
  *Output:* "Our current developers are using Claude Code plus Novita DeepSeek."

### Correctness — is the error actually fixed, with no new error?

- **0** — The error survives, or a new one appeared.
  *Input:* "I has finish the task yesterday."
  *Output:* "I has finished the task yesterday."
- **1** — The error is fixed, but the fix is awkward, or it drags in a smaller
  new infelicity.
  *Output:* "I have finished the task yesterday." — grammatical, but the
  present perfect sits badly with "yesterday"; "I finished" is the natural fix.
- **2** — The error is fixed cleanly and nothing new is wrong.
  *Output:* "I finished the task yesterday."

### Voice preservation — does it still sound like the same writer?

- **0** — The writer disappeared: contractions expanded, hedges deleted,
  informality ironed out, or a greeting or closing added.
  *Input:* "In terms of scope, I guess around 1-2 hours."
  *Output:* "Regarding the scope of this work, the estimated duration is
  approximately one to two hours."
- **1** — Mostly intact, but one voice marker was lost — a hedge, a
  contraction, an abbreviation, or an @mention form.
  *Output:* "In terms of scope, it is around 1-2 hours." — "I guess" is gone.
- **2** — Every voice marker survives.
  *Output:* "In terms of scope, I guess around 1-2 hours."
```

- [ ] **Step 2: Write the failing rubric test**

```python
import re
from pathlib import Path

import slackchat.eval.review as review_module
from slackchat.core.prompts import parse_frontmatter
from slackchat.eval.review import DIMENSIONS, rubric_version

RUBRIC = Path(review_module.__file__).parent / "rubric.md"


def _rubric_text():
    meta, body = parse_frontmatter(RUBRIC.read_text(encoding="utf-8"))
    return meta, body


def test_rubric_is_versioned():
    meta, _ = _rubric_text()
    assert meta["version"] == "1"
    assert rubric_version() == "1"


def test_the_seven_dimensions_from_the_spec_are_present():
    assert DIMENSIONS["translation"] == ("Adequacy", "Naturalness", "Voice compliance", "Concision")
    assert DIMENSIONS["correction"] == ("Minimality", "Correctness", "Voice preservation")


def test_every_dimension_has_a_heading_in_the_rubric():
    _, body = _rubric_text()
    for dimensions in DIMENSIONS.values():
        for name in dimensions:
            assert f"### {name}" in body, name


def test_every_dimension_anchors_all_three_levels():
    _, body = _rubric_text()
    sections = re.split(r"^### ", body, flags=re.MULTILINE)[1:]
    assert len(sections) == 7
    for section in sections:
        for level in ("**0**", "**1**", "**2**"):
            assert level in section, section.splitlines()[0]


def test_every_level_carries_a_concrete_example():
    _, body = _rubric_text()
    sections = re.split(r"^### ", body, flags=re.MULTILINE)[1:]
    for section in sections:
        assert section.count("*Output:*") >= 3, section.splitlines()[0]


def test_the_tie_break_rule_is_stated():
    _, body = _rubric_text()
    assert "take the lower one" in body


def test_the_scale_is_zero_one_two_not_one_to_five():
    _, body = _rubric_text()
    assert "Scale: 0, 1, 2" in body
```

- [ ] **Step 3: Write the failing review test**

```python
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
```

- [ ] **Step 4: Run both tests to verify they fail**

Run: `uv run pytest tests/test_rubric.py tests/test_review.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.eval.review'`

- [ ] **Step 5: Write `src/slackchat/eval/review.py`**

```python
"""Human scoring against the rubric. Phase 1 has no LLM judge on purpose.

Human scores are the real ground truth, and later the calibration set for a
judge. The ``reviewer`` column is in the primary key from the start, so
measuring judge-human agreement in Phase 2 is a JOIN, not a migration.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from slackchat.core.prompts import parse_frontmatter
from slackchat.store import sqlite as store

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "translation": ("Adequacy", "Naturalness", "Voice compliance", "Concision"),
    "correction": ("Minimality", "Correctness", "Voice preservation"),
}

_RUBRIC_PATH = Path(__file__).resolve().parent / "rubric.md"
VALID_SCORES = {"0", "1", "2"}


def rubric_version() -> str:
    meta, _ = parse_frontmatter(_RUBRIC_PATH.read_text(encoding="utf-8"))
    return meta.get("version", "0")


def unreviewed_runs(
    conn: sqlite3.Connection, limit: int, reviewer: str = "human"
) -> list[sqlite3.Row]:
    """Eval runs this reviewer has not scored yet, oldest first."""
    return list(
        conn.execute(
            """
            SELECT r.* FROM runs r
            WHERE r.client = 'eval'
              AND r.error IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM reviews v
                WHERE v.run_id = r.run_id AND v.reviewer = ?
              )
            ORDER BY r.created_at ASC, r.rowid ASC
            LIMIT ?
            """,
            (reviewer, limit),
        )
    )


def review_session(
    conn: sqlite3.Connection,
    *,
    limit: int,
    read_line: Callable[[str], str],
    write: Callable[[str], None],
    clock: Callable[[], str],
    reviewer: str = "human",
) -> int:
    """Score runs one at a time. Returns how many were fully scored.

    Scores for a run are written only after every dimension is answered, so
    an interrupted session leaves no half-scored run behind to skew an
    agreement calculation later.
    """
    runs = unreviewed_runs(conn, limit, reviewer)
    if not runs:
        write("nothing to review\n")
        return 0

    write(f"rubric version {rubric_version()} — scores are 0, 1 or 2\n")
    scored = 0
    for index, row in enumerate(runs, start=1):
        write(f"\n[{index}/{len(runs)}] {row['run_id']}  {row['mode']}\n")
        write(f"  in : {row['input']}\n")
        write(f"  out: {row['output']}\n")

        pending: list[tuple[str, int]] = []
        try:
            for dimension in DIMENSIONS[row["mode"]]:
                pending.append((dimension, _ask_score(dimension, read_line)))
            note = read_line("  note (optional): ").strip() or None
        except EOFError:
            write("\nstopped\n")
            break

        for dimension, score in pending:
            store.insert_review(
                conn,
                run_id=row["run_id"],
                dimension=dimension,
                score=score,
                reviewer=reviewer,
                note=note,
                created_at=clock(),
            )
        scored += 1

    write(f"\nscored {scored} run(s)\n")
    return scored


def _ask_score(dimension: str, read_line: Callable[[str], str]) -> int:
    while True:
        answer = read_line(f"  {dimension} [0/1/2]: ").strip()
        if answer in VALID_SCORES:
            return int(answer)
```

- [ ] **Step 6: Wire `--review` into the eval subcommand**

In `src/slackchat/cli/main.py`, extend `_cmd_eval`:

```python
def _cmd_eval(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat eval")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None)
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--limit", type=int, default=20, help="runs to review")
    args = parser.parse_args(argv)

    if args.compare:
        return eval_compare(args.compare[0], args.compare[1])

    if args.review:
        conn = store.connect()
        try:
            review_session(
                conn,
                limit=args.limit,
                read_line=input,
                write=lambda chunk: print(chunk, end=""),
                clock=utc_now,
            )
        finally:
            conn.close()
        return EXIT_OK

    run_suite(build_service())
    return EXIT_OK
```

Imports to add:

```python
from slackchat.eval.review import review_session
```

`utc_now` needs a home outside `core/`, since `cli/` should not reach into pipeline internals. Add to `src/slackchat/config.py`:

```python
def utc_now() -> str:
    """ISO8601 UTC, second precision, ``Z`` suffix. Matches Result.created_at."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
```

and import it in `cli/main.py` as `from slackchat.config import utc_now`. Then change `core/pipeline.py`'s `_utc_now` to keep its own copy (core may not import config) — the duplication is two lines and the alternative is a boundary violation.

- [ ] **Step 7: Run both tests to verify they pass**

Run: `uv run pytest tests/test_rubric.py tests/test_review.py -q`
Expected: PASS, 7 + 11 tests.

- [ ] **Step 8: Manual verification**

```bash
uv run slackchat eval                 # populates eval runs
uv run slackchat eval --review --limit 5
sqlite3 "${XDG_DATA_HOME:-$HOME/.local/share}/slackchat/runs.db" \
  "SELECT run_id, dimension, score, reviewer FROM reviews ORDER BY run_id;"
```

Score five cases. Expected: three prompts for a correction run, four for a translation run, an invalid entry re-prompting rather than crashing, and rows in `reviews` with `reviewer = 'human'`.

While scoring, watch whether you can pick a level without re-reading the rubric. If you cannot, the anchor for that level is too vague — fix `rubric.md` and bump its `version:`.

- [ ] **Step 9: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/eval/rubric.md src/slackchat/eval/review.py src/slackchat/config.py src/slackchat/core/pipeline.py src/slackchat/cli/main.py tests/test_rubric.py tests/test_review.py
git commit -m "feat: add anchored rubric and human review session"
```

---

### Task 14: Local HTTP daemon

Covers spec slice 10 and §11. The daemon holds no logic of its own — it calls `service.run()` and serialises the `Result`. That is the proof of "one shared core service", so any logic that creeps in here is a bug.

**Security note worth reading before writing code:** any page open in the browser can `fetch('http://127.0.0.1:8765/…')` from its own JavaScript. Binding to loopback is not access control. The token header is what makes this safe, so it is not optional and it has no "skip in dev" flag.

**Files:**
- Create: `src/slackchat/server/app.py`
- Create: `src/slackchat/server/token.py`
- Modify: `src/slackchat/cli/main.py` (`serve` subcommand)
- Test: `tests/test_server_token.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `slackchat.service.build_service`, `slackchat.config.{Config, ServerConfig, config_dir, load_config}`, `slackchat.core.types.EmptyInputError`
- Produces:
  - `slackchat.server.token.TOKEN_HEADER = "X-Slackchat-Token"`
  - `slackchat.server.token.token_file() -> Path`
  - `slackchat.server.token.resolve_token(config: Config) -> str`
  - `slackchat.server.app.create_app(service=None, config=None, token=None) -> FastAPI`
  - `slackchat.server.app.serve(config: Config | None = None) -> int`

- [ ] **Step 1: Write the failing token test**

```python
import pytest

from slackchat.config import Config, ServerConfig, config_dir
from slackchat.server import token as tok


def test_a_hand_set_config_token_wins(isolated_paths):
    config = Config(server=ServerConfig(token="from-config"))
    assert tok.resolve_token(config) == "from-config"


def test_a_token_is_generated_and_persisted_on_first_use(isolated_paths):
    generated = tok.resolve_token(Config())
    assert len(generated) >= 32
    assert tok.token_file().read_text(encoding="utf-8").strip() == generated


def test_the_persisted_token_is_reused(isolated_paths):
    first = tok.resolve_token(Config())
    assert tok.resolve_token(Config()) == first


def test_the_token_lives_beside_the_config_file(isolated_paths):
    tok.resolve_token(Config())
    assert tok.token_file().parent == config_dir()


def test_the_token_file_is_not_world_readable(isolated_paths):
    tok.resolve_token(Config())
    assert oct(tok.token_file().stat().st_mode)[-3:] == "600"


def test_the_env_var_overrides_everything(isolated_paths, monkeypatch):
    monkeypatch.setenv("SLACKCHAT_SERVER_TOKEN", "from-env")
    config = Config(server=ServerConfig(token="from-config"))
    assert tok.resolve_token(config) == "from-env"


def test_the_header_name_is_stable(isolated_paths):
    # The Phase 2 extension will hardcode this; changing it breaks the client.
    assert tok.TOKEN_HEADER == "X-Slackchat-Token"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_server_token.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.server.token'`

- [ ] **Step 3: Write `src/slackchat/server/token.py`**

```python
"""Shared-secret token for the loopback daemon.

Stored in its own file rather than written back into ``config.toml``: there is
no TOML writer in the stdlib, and appending a second ``[server]`` table to a
hand-edited config would make it unparseable. A hand-set ``[server] token`` in
config.toml still wins, so the spec's intent is preserved.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from slackchat.config import Config, config_dir

TOKEN_HEADER = "X-Slackchat-Token"
TOKEN_FILENAME = "server_token"
TOKEN_BYTES = 32


def token_file() -> Path:
    return config_dir() / TOKEN_FILENAME


def resolve_token(config: Config) -> str:
    """Env var, then config.toml, then a generated-and-persisted secret."""
    from_env = os.environ.get("SLACKCHAT_SERVER_TOKEN")
    if from_env:
        return from_env
    if config.server.token:
        return config.server.token

    path = token_file()
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    generated = secrets.token_urlsafe(TOKEN_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generated + "\n", encoding="utf-8")
    path.chmod(0o600)
    return generated
```

- [ ] **Step 4: Write the failing server test**

```python
import pytest
from fastapi.testclient import TestClient

from slackchat import service as svc
from slackchat.config import CliConfig, Config, ServerConfig
from slackchat.server.app import create_app
from slackchat.server.token import TOKEN_HEADER
from slackchat.store import sqlite as store

TOKEN = "test-token"


@pytest.fixture
def client(isolated_paths, fake_provider):
    def _client(replies, *, error=None, origins=()):
        provider = fake_provider(replies, error=error)
        config = Config(server=ServerConfig(port=8765, token=TOKEN, allowed_origins=tuple(origins)))
        service = svc.build_service(config, provider=provider)
        app = create_app(service=service, config=config, token=TOKEN)
        return TestClient(app), provider

    return _client


def _headers():
    return {TOKEN_HEADER: TOKEN}


def test_health_needs_no_token(client):
    api, _ = client([])
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_process_returns_the_result_as_json(client):
    api, _ = client(["I finished the task yesterday."])
    response = api.post(
        "/process", json={"text": "I has finish the task yesterday."}, headers=_headers()
    )
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == "I finished the task yesterday."
    assert body["mode"] == "correction"
    assert body["forced"] is False
    assert body["changed_ratio"] == 0.3333
    assert body["flags"] == []
    assert body["error"] is None
    assert body["prompt_version"] == "1"
    assert len(body["prompt_hash"]) == 12
    assert body["cost_usd"] == pytest.approx(0.0002)


def test_the_json_carries_the_diff_segments(client):
    api, _ = client(["I finished the task yesterday."])
    body = api.post(
        "/process", json={"text": "I has finish the task yesterday."}, headers=_headers()
    ).json()
    kinds = [c["kind"] for c in body["changes"]]
    assert kinds == ["equal", "replace", "equal"]
    assert body["changes"][1]["before"] == "has finish"
    assert body["changes"][1]["after"] == "finished"


def test_the_json_shape_matches_what_the_cli_saw(client):
    api, provider = client(["I finished the task yesterday."] * 2)
    body = api.post(
        "/process", json={"text": "I has finish the task yesterday."}, headers=_headers()
    ).json()
    direct = svc.build_service(
        Config(server=ServerConfig(token=TOKEN)), provider=provider
    ).run("I has finish the task yesterday.", client="cli")
    assert set(body) == {f.name for f in direct.__dataclass_fields__.values()}


def test_an_explicit_mode_is_honoured(client):
    api, _ = client(["I am done."])
    body = api.post(
        "/process", json={"text": "Tôi đã xong", "mode": "correction"}, headers=_headers()
    ).json()
    assert body["mode"] == "correction"
    assert body["forced"] is True


def test_a_missing_token_is_rejected(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "hello"})
    assert response.status_code == 401
    assert provider.calls == []


def test_a_wrong_token_is_rejected(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "hello"}, headers={TOKEN_HEADER: "nope"})
    assert response.status_code == 401
    assert provider.calls == []


def test_empty_text_is_a_400_and_costs_nothing(client):
    api, provider = client(["never used"])
    response = api.post("/process", json={"text": "   "}, headers=_headers())
    assert response.status_code == 400
    assert provider.calls == []
    conn = store.connect()
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_a_bad_mode_value_is_a_422(client):
    api, _ = client([])
    response = api.post("/process", json={"text": "hi", "mode": "rewrite"}, headers=_headers())
    assert response.status_code == 422


def test_a_provider_error_is_a_200_with_the_error_in_the_body(client):
    api, _ = client([], error="rate limited")
    response = api.post("/process", json={"text": "hello there"}, headers=_headers())
    assert response.status_code == 200
    assert response.json()["error"] == "rate limited"


def test_runs_are_logged_with_the_server_client(client):
    api, _ = client(["I finished"])
    api.post("/process", json={"text": "I has finish"}, headers=_headers())
    conn = store.connect()
    assert conn.execute("SELECT client FROM runs").fetchone()[0] == "server"


def test_no_cors_headers_without_an_allowlist(client):
    api, _ = client(["out"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "https://evil.example"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_an_allowlisted_origin_gets_the_cors_header(client):
    api, _ = client(["out"], origins=["chrome-extension://abcd"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "chrome-extension://abcd"},
    )
    assert response.headers["access-control-allow-origin"] == "chrome-extension://abcd"


def test_a_non_allowlisted_origin_gets_no_cors_header(client):
    api, _ = client(["out"], origins=["chrome-extension://abcd"])
    response = api.post(
        "/process",
        json={"text": "hello"},
        headers={**_headers(), "Origin": "chrome-extension://evil"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_the_server_module_contains_no_pipeline_logic():
    import inspect

    from slackchat.server import app as module

    source = inspect.getsource(module)
    for forbidden in ("difflib", "sanitize", "detect(", "mechanical_replace", "find_violations"):
        assert forbidden not in source, forbidden
```

- [ ] **Step 5: Run it to verify it fails**

Run: `uv run pytest tests/test_server.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'slackchat.server.app'`

- [ ] **Step 6: Write `src/slackchat/server/app.py`**

```python
"""FastAPI daemon on 127.0.0.1. Calls process(), serialises the Result, logs.

There is deliberately nothing else in this module. If a behaviour appears here
that the CLI does not have, the "one shared core service" property is gone.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from slackchat.config import Config, load_config
from slackchat.core.types import EmptyInputError
from slackchat.server.token import TOKEN_HEADER, resolve_token
from slackchat.service import Service, build_service

BIND_HOST = "127.0.0.1"


class ProcessRequest(BaseModel):
    text: str
    mode: Literal["correction", "translation"] | None = None


def create_app(
    service: Service | None = None,
    config: Config | None = None,
    token: str | None = None,
) -> FastAPI:
    resolved_config = config if config is not None else load_config()
    resolved_token = token if token is not None else resolve_token(resolved_config)
    resolved_service = service if service is not None else build_service(resolved_config)

    app = FastAPI(title="slackchat", docs_url=None, redoc_url=None)

    if resolved_config.server.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_config.server.allowed_origins),
            allow_methods=["POST", "GET"],
            allow_headers=[TOKEN_HEADER, "Content-Type"],
        )

    def require_token(
        provided: str | None = Header(default=None, alias=TOKEN_HEADER),
    ) -> None:
        # Loopback is not access control: any open page can fetch 127.0.0.1.
        if provided != resolved_token:
            raise HTTPException(status_code=401, detail="missing or invalid token")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/process", dependencies=[Depends(require_token)])
    def process_endpoint(payload: ProcessRequest) -> dict:
        try:
            result = resolved_service.run(payload.text, payload.mode, client="server")
        except EmptyInputError as exc:
            raise HTTPException(status_code=400, detail="input is empty") from exc
        return dataclasses.asdict(result)

    return app


def serve(config: Config | None = None) -> int:
    """Run the daemon on loopback only."""
    import uvicorn

    resolved = config if config is not None else load_config()
    token = resolve_token(resolved)
    print(f"slackchat serving on http://{BIND_HOST}:{resolved.server.port}")
    print(f"{TOKEN_HEADER}: {token}")
    uvicorn.run(
        create_app(config=resolved, token=token),
        host=BIND_HOST,
        port=resolved.server.port,
        log_level="warning",
    )
    return 0
```

- [ ] **Step 7: Add the `serve` subcommand**

In `src/slackchat/cli/main.py`:

```python
def _cmd_serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slackchat serve")
    parser.parse_args(argv)
    from slackchat.server.app import serve

    return serve()
```

Route it:

```python
        if command == "serve":
            return _cmd_serve(rest)
```

The `serve` import stays local to the function so that `slackchat "text"` does not pay FastAPI's import cost on every invocation.

Then delete the "not implemented yet" fallback branch in `main` — every subcommand in `SUBCOMMANDS` now has a handler. Replace it with:

```python
        raise AssertionError(f"unrouted subcommand {command!r}")
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_server_token.py tests/test_server.py -q`
Expected: PASS, 7 + 15 tests.

- [ ] **Step 9: Manual verification against the CLI**

In one terminal:

```bash
uv run slackchat serve
```

Note the printed token. In another terminal:

```bash
TOKEN=<paste>
curl -s http://127.0.0.1:8765/health
curl -s -X POST http://127.0.0.1:8765/process \
  -H "Content-Type: application/json" \
  -d '{"text":"I has finish the task yesterday."}' | head -c 200          # expect 401
curl -s -X POST http://127.0.0.1:8765/process \
  -H "Content-Type: application/json" -H "X-Slackchat-Token: $TOKEN" \
  -d '{"text":"I has finish the task yesterday."}'
uv run slackchat --raw "I has finish the task yesterday."
```

Expected: `{"status":"ok"}`; a 401 without the token; with the token, JSON whose `output` matches what the CLI prints for the same input; and `client = 'server'` on the new row:

```bash
sqlite3 "${XDG_DATA_HOME:-$HOME/.local/share}/slackchat/runs.db" \
  "SELECT client, mode, output FROM runs ORDER BY created_at DESC LIMIT 2;"
```

Also confirm the bind is loopback-only — from another machine on the LAN, `curl http://<this-host>:8765/health` must fail to connect.

- [ ] **Step 10: Commit**

```bash
uv run pytest -q && uv run lint-imports
git add src/slackchat/server src/slackchat/cli/main.py tests/test_server_token.py tests/test_server.py
git commit -m "feat: add loopback HTTP daemon with token auth and CORS allowlist"
```

---

### Task 15: CI enforcement and a documented example config

Spec §4 says the import boundary is enforced "in CI". Nothing enforces it until there is a CI job.

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `config.example.toml`
- Modify: `AGENTS.md` (add the config and CI lines)
- Test: none new — this task's test is CI going green.

**Interfaces:**
- Consumes: every command established in earlier tasks.
- Produces: nothing importable.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --locked
      - name: tests
        run: uv run pytest -q
      - name: architecture boundaries
        run: uv run lint-imports
```

No `ANTHROPIC_API_KEY` secret is configured, and none is needed: every test injects `FakeProvider`. If a test ever needs a key, that test is reaching the network and should be fixed instead.

The clipboard tests patch `subprocess.run`, so the absence of `pbcopy` on Linux does not matter. If any clipboard test fails on the runner, it is patching the wrong seam.

- [ ] **Step 2: Verify the CI commands locally exactly as CI runs them**

```bash
uv sync --locked
uv run pytest -q
uv run lint-imports
```

Expected: all green. If `uv sync --locked` fails, `uv.lock` is stale — run `uv lock` and commit it.

- [ ] **Step 3: Write `config.example.toml`**

The real config lives at `~/.config/slackchat/config.toml`; this file is documentation with every default spelled out.

```toml
# Copy to ~/.config/slackchat/config.toml and edit. Every key is optional;
# the values shown are the defaults.

[provider]
name  = "anthropic"
model = "claude-haiku-4-5"

[limits]
# Correction only: fraction of input tokens allowed to change before the
# output is treated as over-edited. Raising this weakens the project's
# primary guarantee — tighten the prompt instead.
max_changed_ratio = 0.25
# Eval assertion only: len(output) / len(input) in words.
max_length_ratio  = 1.5
max_retries       = 1

[cli]
# Copy the result to the clipboard when stdout is a terminal.
auto_copy = true

[server]
port = 8765
# Leave unset to have a token generated into ~/.config/slackchat/server_token
# on first `slackchat serve`.
# token = "..."
# Origins allowed to call the daemon from a browser. Empty means none.
allowed_origins = []
```

The API key is not in this file and never should be: `ANTHROPIC_API_KEY` comes from the environment.

- [ ] **Step 4: Add the missing lines to `AGENTS.md`**

Under `## Commands`, append:

```markdown
- Review scoring: `uv run slackchat eval --review --limit 5`
- Compare two prompt versions: `uv run slackchat eval --compare 1 2`
- CI runs exactly: `uv sync --locked`, `uv run pytest -q`, `uv run lint-imports`
```

Add a new section:

```markdown
## Config

Defaults live in `src/slackchat/config.py`; `config.example.toml` documents
them. The user's real config is `~/.config/slackchat/config.toml`. Tests must
never touch it — use the `isolated_paths` fixture, which points
`SLACKCHAT_CONFIG` and `SLACKCHAT_DB` at `tmp_path`.

Raising `max_changed_ratio` to make an eval case pass is the wrong fix. The
right fix is a tighter prompt and a bumped `version:`.
```

- [ ] **Step 5: Full verification**

```bash
uv run pytest -q
uv run lint-imports
uv run slackchat detect "Cà phê ở đây ngon."
uv run slackchat "The deployment failed because the config was missing."
uv run slackchat eval
uv run slackchat log --last 5
```

Expected: tests green, contracts kept, `translation`, the already-correct sentence returned unchanged at `changed 0%`, an eval pass rate with a real cost, and five logged rows.

- [ ] **Step 6: Commit**

```bash
git add .github config.example.toml AGENTS.md
git commit -m "chore: enforce tests and import contracts in CI, document config"
```

---

## Slice-to-task map

Spec §12's verification table, mapped to the tasks that deliver it.

| Spec slice | Task | Verified by |
|---|---|---|
| 1 `detect` | 1 | the VN/EN table including `café`, `résumé`; no API key |
| 2 `correct` | 8 | `slackchat "I has finish"` returns corrected text |
| 3 diff render, `--raw`, auto-copy | 8, 9 | coloured output; `--raw \| pbcopy`; redirect copies nothing |
| 4 REPL + banner | 10 | banner once, multi-line paste is one run, `/exit` leaves |
| 5 `translate` + auto-route | 8 | two sentences, two languages, the right mode each time |
| 6 validate + retry + flags | 4, 7 | deliberately breaking inputs raise the expected flags |
| 7 logging | 11 | three commands, then query `runs.db` |
| 8 eval assertions | 12 | `slackchat eval` prints a pass rate and a real cost |
| 9 rubric + `--review` | 13 | score 5 cases, query `reviews` |
| 10 `serve` | 14 | `curl` returns the same JSON the CLI rendered |

Tasks 1 and 10 run without an API key, as spec §12 requires: task 1 is pure, and task 10's model calls go through `FakeProvider` in tests, leaving the banner, prompts, multi-line handling and exit paths verifiable offline.

## What Phase 1 deliberately does not build

Spec §15, restated so no executor adds it: no browser extension, no LLM judge or agreement measurement, no replay eval from real logs, no local model provider. Each has its seam already cut — the extension has the HTTP contract, the judge has the `reviewer` column, replay has the `runs` table, a local model has the `Provider` protocol.
