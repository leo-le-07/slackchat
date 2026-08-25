import os
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


def test_dotenv_sets_a_missing_var(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text("SLACKCHAT_TEST_KEY=hello\n", encoding="utf-8")
    cfg.load_dotenv(p)
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello"


def test_dotenv_ignores_blank_lines_and_comments(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text("\n# a comment\n\nSLACKCHAT_TEST_KEY=hello\n", encoding="utf-8")
    cfg.load_dotenv(p)
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello"


def test_dotenv_strips_matching_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text('SLACKCHAT_TEST_KEY="hello world"\n', encoding="utf-8")
    cfg.load_dotenv(p)
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello world"


def test_dotenv_supports_export_prefix(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text("export SLACKCHAT_TEST_KEY=hello\n", encoding="utf-8")
    cfg.load_dotenv(p)
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello"


def test_dotenv_never_overrides_an_existing_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACKCHAT_TEST_KEY", "real")
    p = tmp_path / ".env"
    p.write_text("SLACKCHAT_TEST_KEY=from_file\n", encoding="utf-8")
    cfg.load_dotenv(p)
    assert os.environ["SLACKCHAT_TEST_KEY"] == "real"


def test_dotenv_missing_file_is_a_noop(tmp_path):
    cfg.load_dotenv(tmp_path / "missing.env")  # must not raise


def test_dotenv_defaults_to_a_dotenv_file_in_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACKCHAT_TEST_KEY", raising=False)
    (tmp_path / ".env").write_text("SLACKCHAT_TEST_KEY=hello\n", encoding="utf-8")
    cfg.load_dotenv()
    assert os.environ["SLACKCHAT_TEST_KEY"] == "hello"
