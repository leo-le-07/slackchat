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
