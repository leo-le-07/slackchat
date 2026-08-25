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
