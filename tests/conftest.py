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
