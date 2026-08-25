"""Deterministic Vietnamese/English detection. Pure, no network, no LLM."""

from __future__ import annotations

import re
import unicodedata

from slackchat.core.types import Mode

# Letters that occur in Vietnamese and in no English loanword. Decisive on sight.
VN_EXCLUSIVE = frozenset("ăằắẳẵặơờớởỡợưừứửữựđ")

# Letters that occur in Vietnamese but also in borrowed English spellings.
# Only counted after allowlisted loanwords are removed.
VN_MARKED = frozenset("áàảãạâầấẩẫậéèẻẽẹêềếểễệíìỉĩịóòỏõọôồốổỗộúùủũụýỳỷỹỵ")

# Accented words an English writer may legitimately type. Kept deliberately
# small: only entries whose accents fall inside VN_MARKED can ever matter.
LOANWORDS: tuple[str, ...] = (
    "café",
    "cafés",
    "canapé",
    "château",
    "cliché",
    "clichés",
    "cortège",
    "crème brûlée",
    "crème",
    "brûlée",
    "crêpe",
    "crêpes",
    "décor",
    "déjà vu",
    "déjà",
    "début",
    "débuts",
    "éclair",
    "élite",
    "entrée",
    "entrées",
    "exposé",
    "façade",
    "fête",
    "fiancé",
    "fiancée",
    "matériel",
    "mêlée",
    "naïveté",
    "papier-mâché",
    "pâté",
    "pièce",
    "protégé",
    "protégée",
    "résumé",
    "résumés",
    "rôle",
    "séance",
    "soirée",
    "soupçon",
    "touché",
    "à la carte",
    "tête-à-tête",
    "vis-à-vis",
    "apéritif",
)

# Longest-first so "crème brûlée" wins over "crème". Lookarounds instead of \b
# so that hyphenated entries such as "vis-à-vis" match as a whole.
_LOANWORD_ALTERNATION = "|".join(sorted((re.escape(w) for w in LOANWORDS), key=len, reverse=True))
_LOANWORD_RE = re.compile(
    rf"(?<!\w)(?:{_LOANWORD_ALTERNATION})(?!\w)",
    re.IGNORECASE,
)


def detect(text: str) -> Mode:
    """Return the mode implied by ``text``.

    Vietnamese input means translation mode. Anything else means correction
    mode. There is no grey zone and no clarifying prompt: ``--mode`` is the
    only escape hatch.
    """
    normalised = unicodedata.normalize("NFC", text).lower()
    if VN_EXCLUSIVE & frozenset(normalised):
        return "translation"
    without_loanwords = _LOANWORD_RE.sub(" ", normalised)
    if VN_MARKED & frozenset(without_loanwords):
        return "translation"
    return "correction"
