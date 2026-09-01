"""Spoken *action* commands. Matched on a whole Fn+Cmd utterance."""

from __future__ import annotations

import re
from dataclasses import dataclass

ENTER = "enter"
BACKSPACE = "backspace"
DELETE_WORD = "delete_word"
DELETE_SENTENCE = "delete_sentence"
SCRATCH = "scratch"

# Longer first so "delete last word" wins over "delete".
_PHRASES: tuple[tuple[str, str], ...] = (
    ("delete the last sentence", DELETE_SENTENCE),
    ("delete last sentence", DELETE_SENTENCE),
    ("scratch last sentence", DELETE_SENTENCE),
    ("delete the last word", DELETE_WORD),
    ("delete last word", DELETE_WORD),
    ("scratch last word", DELETE_WORD),
    ("backspace word", DELETE_WORD),
    ("delete word", DELETE_WORD),
    ("scratch that", SCRATCH),
    ("undo that", SCRATCH),
    ("delete that", SCRATCH),
    ("backspace", BACKSPACE),
    ("enter", ENTER),
)

_PHRASE_TOKENS: tuple[tuple[tuple[str, ...], str], ...] = tuple(
    (tuple(phrase.split()), action) for phrase, action in _PHRASES
)

_LABELS = {
    ENTER: "Enter",
    BACKSPACE: "Backspace",
    DELETE_WORD: "Delete word",
    DELETE_SENTENCE: "Delete sentence",
    SCRATCH: "Scratch that",
}


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float

    @property
    def norm(self) -> str:
        return _norm_token(self.text)


def norm_token(text: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", text.strip()).lower()


_norm_token = norm_token


def action_label(action: str) -> str:
    return _LABELS.get(action, action)


def match_action(text: str) -> str | None:
    """Return an action id if the whole utterance is exactly one command phrase."""
    compact = text.strip()
    if not compact:
        return None
    parts = [_norm_token(p) for p in re.split(r"\s+", compact) if _norm_token(p)]
    if not parts:
        return None
    tokens = tuple(parts)
    for phrase, action in _PHRASE_TOKENS:
        if tokens == phrase:
            return action
    return None


def last_sentence_chars(text: str) -> int:
    """Characters to backspace to remove the last sentence of `text`."""
    stripped = text.rstrip()
    trailing = len(text) - len(stripped)
    if not stripped:
        return len(text)
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    if len(parts) <= 1:
        return len(text)
    last = parts[-1]
    return len(last) + trailing + 1


def trim_last_word(text: str) -> str:
    return re.sub(r"\s*\S+\s*$", "", text)
