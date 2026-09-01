"""Filler-word, dictation-command, and Whisper-artifact cleanup."""

from __future__ import annotations

import re

from sonoscribe.commands import apply_commands
from sonoscribe.lexicon import correct_product_name

_ARTIFACTS = [
    r"\[BLANK_AUDIO\]",
    r"\[INAUDIBLE\]",
    r"\[MUSIC\]",
    r"\[APPLAUSE\]",
    r"\[NOISE\]",
    r"\(pause\)",
    r"\(music\)",
    r"\(applause\)",
]

# Longer phrases first so they win over inner words.
_FILLERS = [
    "you know",
    "i mean",
    "kind of",
    "sort of",
    "kinda",
    "sorta",
    "umm",
    "uhh",
    "hmm",
    "mmm",
    "um",
    "uh",
    "mm",
    "ah",
    "er",
    "huh",
]

_WATCHING = re.compile(
    r"(?i)(?:thanks for watching|thank you for watching)[.!?]*\s*$"
)
_THANK_YOU = re.compile(r"(?i)(?:^|\s)thank you[.!?]*\s*$")
_COMMA_SPACE = re.compile(r"\s+,+")
_LEADING_COMMAS = re.compile(r"^,+\s*")
_MULTI_SPACE = re.compile(r"[^\S\n]{2,}")
_TRIM_PUNCT = ",;"

_FILLER_PATTERNS = [
    re.compile(
        rf"(?i)(?<![A-Za-z0-9]){re.escape(filler)}(?![A-Za-z0-9])[,.]?"
    )
    for filler in _FILLERS
]

_DOMAIN_TOKEN = re.compile(
    r"(?i)\b(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s]*)?"
)
_NAVIGABLE = re.compile(
    r"(?i)^(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s]*)?$"
)
_EMAIL = re.compile(r"(?i)^[^\s@]+@[^\s@]+\.[a-z]{2,}$")


def strip_fillers(raw: str) -> str:
    text = raw
    for pattern in _ARTIFACTS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = _WATCHING.sub("", text)
    text = _THANK_YOU.sub("", text)
    for filler_re in _FILLER_PATTERNS:
        text = filler_re.sub(" ", text)
    return text


def normalize_domains(text: str) -> str:
    return _DOMAIN_TOKEN.sub(lambda match: match.group(0).lower(), text)


def _looks_navigable(text: str) -> bool:
    trimmed = text.strip().rstrip(".")
    return bool(_NAVIGABLE.fullmatch(trimmed) or _EMAIL.fullmatch(trimmed))


def finalize(text: str) -> str:
    text = _COMMA_SPACE.sub(",", text)
    text = _LEADING_COMMAS.sub("", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = text.strip().strip(_TRIM_PUNCT).strip()
    if not text:
        return ""
    if _looks_navigable(text):
        return text.rstrip(".")
    if text[0].isalpha():
        return text[0].upper() + text[1:]
    return text


def clean(raw: str) -> str:
    return finalize(normalize_domains(strip_fillers(apply_commands(correct_product_name(raw)))))


def process(raw: str, remove_fillers: bool = True) -> str:
    text = apply_commands(correct_product_name(raw))
    if remove_fillers:
        text = strip_fillers(text)
    return finalize(normalize_domains(text))
