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
