"""Clipboard access. A CLI concern only; ``core/`` knows nothing about it."""

from __future__ import annotations

import subprocess

PBCOPY = "pbcopy"


def copy(text: str) -> bool:
    """Put ``text`` on the macOS clipboard. Never raises.

    A missing or failing ``pbcopy`` is a convenience that did not happen, not
    an error worth failing the run over. macOS-only is accepted for Phase 1.
    """
    try:
        subprocess.run([PBCOPY], input=text.encode("utf-8"), check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
