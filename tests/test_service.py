import pytest

from slackchat import service as svc
from slackchat.config import Config, ProviderConfig
from slackchat.core.types import EmptyInputError, Limits


def test_build_service_uses_the_injected_provider(isolated_paths, fake_provider):
    provider = fake_provider("out")
    service = svc.build_service(Config(), provider=provider)
    result = service.run("out", client="cli")
    assert result.output == "out"
    assert result.provider == "fake"


def test_the_real_prompt_and_price_table_are_wired_in(isolated_paths, fake_provider):
    provider = fake_provider("The deployment failed.")
    service = svc.build_service(Config(), provider=provider)
    result = service.run("The deployment failed.", client="cli")
    assert result.prompt_version == "3"
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
    correction = service.run("a", client="cli")
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
