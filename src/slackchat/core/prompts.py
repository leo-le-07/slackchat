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
