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
    show_status: bool = False


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


def config_dir() -> Path:
    """Directory holding config.toml and the server token file."""
    explicit = os.environ.get("SLACKCHAT_CONFIG")
    if explicit:
        return Path(explicit).parent
    return Path.cwd() / ".config"


def config_path() -> Path:
    explicit = os.environ.get("SLACKCHAT_CONFIG")
    if explicit:
        return Path(explicit)
    return config_dir() / "config.toml"


def db_path() -> Path:
    explicit = os.environ.get("SLACKCHAT_DB")
    if explicit:
        return Path(explicit)
    return Path.cwd() / "data" / "runs.db"


def load_dotenv(path: Path | None = None) -> None:
    """Populate ``os.environ`` from a ``.env`` file (default: ``./.env``).

    A real shell export always wins: an existing key is never overridden. A
    missing file is not an error, same reasoning as :func:`load_config` — the
    file is optional convenience, not a requirement.
    """
    target = path if path is not None else Path.cwd() / ".env"
    if not target.exists():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def utc_now() -> str:
    """ISO8601 UTC, second precision, ``Z`` suffix. Matches Result.created_at."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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
        cli=CliConfig(
            auto_copy=bool(cli_raw.get("auto_copy", defaults.cli.auto_copy)),
            show_status=bool(cli_raw.get("show_status", defaults.cli.show_status)),
        ),
        server=ServerConfig(
            port=int(server_raw.get("port", defaults.server.port)),
            token=server_raw.get("token", defaults.server.token),
            allowed_origins=tuple(server_raw.get("allowed_origins", ())),
        ),
    )
