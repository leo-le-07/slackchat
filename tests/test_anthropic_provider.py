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
    result = AnthropicProvider(client=_StubClient(_response(blocks))).complete("s", "u", model="m")
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
