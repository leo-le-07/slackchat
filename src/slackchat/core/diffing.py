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
            kind=tag,
            before=" ".join(before_tokens[i1:i2]),
            after=" ".join(after_tokens[j1:j2]),
        )
        changes.append(segment)
        if tag != "equal":
            changed += max(i2 - i1, j2 - j1)

    ratio = changed / len(before_tokens) if before_tokens else (1.0 if after_tokens else 0.0)
    return changes, round(ratio, 4)
