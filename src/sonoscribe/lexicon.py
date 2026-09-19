"""Map Whisper mishearings of the product name and spoken scout/scribe prefixes."""

from __future__ import annotations

import re

# Longer aliases first so they win over inner phrases.
_ALIASES = (
    "so no scribe",
    "sono scribe",
    "suno scribe",
    "sonno scribe",
    "sona scribe",
    "sauna scribe",
    "sonar scribe",
    "sano scribe",
    "sono script",
    "sono stripe",
    "sono-scribe",
    "sunoscribe",
    "sonoscript",
    "sonoscribed",
)

_ALIAS_RES = [
    re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])")
    for alias in _ALIASES
]
_CANONICAL = re.compile(r"(?i)(?<![A-Za-z0-9])sonoscribe(?![A-Za-z0-9])")
_LEAD = frozenset({"a", "the", "ok", "okay", "please", "um", "uh", "hmm", "ah", "er"})
_SCOUT_STRONG = frozenset({"scout", "scouts", "scouted", "task", "tasks", "tasked"})
_SCRIBE_STRONG = frozenset({"scribe", "scribes"})


def correct_product_name(text: str) -> str:
    if not text:
        return ""
    for pattern in _ALIAS_RES:
        text = pattern.sub("Sonoscribe", text)
    return _CANONICAL.sub("Sonoscribe", text)


def correct_scout_prefix(text: str) -> str:
    parts = [part for part in str(text or "").split() if part]
    rest = scout_prefix_rest(parts)
    if rest is None:
        return " ".join(parts)
    return " ".join(["scout", *rest]).strip()


def scout_prefix_rest(tokens: list[str]) -> list[str] | None:
    words = _lead_words(tokens)
    if not words:
        return None
    first, rest = words[0], words[1:]
    if first in _SCOUT_STRONG:
        return rest
    return None


def correct_scribe_prefix(text: str) -> str:
    parts = [part for part in str(text or "").split() if part]
    rest = scribe_prefix_rest(parts)
    if rest is None:
        return " ".join(parts)
    return " ".join(["scribe", *rest]).strip()


def scribe_prefix_rest(tokens: list[str]) -> list[str] | None:
    words = _lead_words(tokens)
    if not words:
        return None
    first, rest = words[0], words[1:]
    if first in _SCRIBE_STRONG:
        return rest
    return None


def _lead_words(tokens: list[str]) -> list[str]:
    words = [_bare_token(item) for item in tokens]
    words = [item for item in words if item]
    while words and words[0] in _LEAD:
        words = words[1:]
    return words


def _bare_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+$", "", str(token or "")).lower()
