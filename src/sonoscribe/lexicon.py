"""Map Whisper mishearings of the product name to Sonoscribe."""

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


def correct_product_name(text: str) -> str:
    if not text:
        return ""
    for pattern in _ALIAS_RES:
        text = pattern.sub("Sonoscribe", text)
    return _CANONICAL.sub("Sonoscribe", text)
