"""A hardcoded 3x5 block font. No dependency, no runtime figlet."""

from __future__ import annotations

GLYPH_HEIGHT = 5
GLYPH_WIDTH = 3

B = "█"  # FULL BLOCK

GLYPHS: dict[str, tuple[str, ...]] = {
    "A": (f"{B}{B}{B}", f"{B} {B}", f"{B}{B}{B}", f"{B} {B}", f"{B} {B}"),
    "C": (f"{B}{B}{B}", f"{B}  ", f"{B}  ", f"{B}  ", f"{B}{B}{B}"),
    "H": (f"{B} {B}", f"{B} {B}", f"{B}{B}{B}", f"{B} {B}", f"{B} {B}"),
    "K": (f"{B} {B}", f"{B} {B}", f"{B}{B} ", f"{B} {B}", f"{B} {B}"),
    "L": (f"{B}  ", f"{B}  ", f"{B}  ", f"{B}  ", f"{B}{B}{B}"),
    "S": (f"{B}{B}{B}", f"{B}  ", f"{B}{B}{B}", f"  {B}", f"{B}{B}{B}"),
    "T": (f"{B}{B}{B}", f" {B} ", f" {B} ", f" {B} ", f" {B} "),
}

WORDMARK = "SLACKCHAT"
HINT = "Ctrl+D or /exit to quit"

DIM = "\x1b[2m"
RESET = "\x1b[0m"


def render_word(word: str) -> str:
    """Lay the glyphs side by side, one blank column between letters."""
    letters = [GLYPHS[ch] for ch in word.upper()]
    return "\n".join(
        " ".join(letter[row] for letter in letters) for row in range(GLYPH_HEIGHT)
    )


def banner(color: bool) -> str:
    hint = f"{DIM}{HINT}{RESET}" if color else HINT
    return f"{render_word(WORDMARK)}\n\n{hint}\n"
