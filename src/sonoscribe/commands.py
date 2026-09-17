"""Spoken dictation commands: 'period' → '.', 'google dot com' → 'google.com'."""

from __future__ import annotations

import re

# Longer phrases first so they win over inner words.
_PHRASES: tuple[tuple[str, str], ...] = (
    ("new paragraph", "\n\n"),
    ("new line", "\n"),
    ("next line", "\n"),
    ("newline", "\n"),
    ("exclamation mark", "!"),
    ("exclamation point", "!"),
    ("question mark", "?"),
    ("open parenthesis", "("),
    ("close parenthesis", ")"),
    ("open paren", "("),
    ("close paren", ")"),
    ("left paren", "("),
    ("right paren", ")"),
    ("open quote", '"'),
    ("close quote", '"'),
    ("double quote", '"'),
    ("semicolon", ";"),
    ("full stop", "."),
    ("fullstop", "."),
    ("at sign", "@"),
    ("at symbol", "@"),
    ("percent sign", "%"),
    ("backslash", "\\"),
    ("underscore", "_"),
    ("hashtag", "#"),
    ("ampersand", "&"),
    ("asterisk", "*"),
    ("ellipsis", "..."),
    ("dot com", ".com"),
    ("dot org", ".org"),
    ("dot net", ".net"),
    ("dot edu", ".edu"),
    ("dot gov", ".gov"),
    ("dot io", ".io"),
    ("dot ai", ".ai"),
    ("dot dev", ".dev"),
    ("dot app", ".app"),
    ("dot co", ".co"),
    ("colon", ":"),
    ("comma", ","),
    ("slash", "/"),
    ("hyphen", "-"),
    ("dash", "-"),
    ("apostrophe", "'"),
    ("period", "."),
    ("quote", '"'),
    ("dot", "."),
)

_PERIOD_OF = re.compile(r"(?i)(?<![A-Za-z0-9])period(?=\s+of\b)")
_PERIOD_GUARD = "\x00PERIODOF\x00"

_PHRASE_RES = [
    (
        re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(spoken)}(?![A-Za-z0-9])"),
        replacement,
    )
    for spoken, replacement in _PHRASES
]

# Command matching wants words. Keep spoken dots/dashes and domains only.
_COMMAND_SPOKEN = {
    spoken
    for spoken, _replacement in _PHRASES
    if spoken == "dot"
    or spoken == "dash"
    or spoken == "hyphen"
    or spoken.startswith("dot ")
}
_COMMAND_PHRASE_RES = [
    pair for pair, (spoken, _replacement) in zip(_PHRASE_RES, _PHRASES) if spoken in _COMMAND_SPOKEN
]

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_SPACE_AFTER_OPEN = re.compile(r"([(\"])\s+")
_SPACE_BEFORE_CLOSE = re.compile(r"\s+([)\"])")
_DOMAIN_DOT = re.compile(
    r"(?i)(?<=[A-Za-z0-9])\s+(\.(?:com|org|net|edu|gov|io|ai|dev|app|co|info|me|us)\b)"
)
_WWW_DOT = re.compile(r"(?i)\bwww\s*\.\s*")
_SPACE_AROUND_NEWLINES = re.compile(r"[^\S\n]*(\n+)[^\S\n]*")
_SLASH_BETWEEN = re.compile(r"(?<=[A-Za-z0-9.])\s+/\s*(?=[A-Za-z0-9])")
_SPACE_AROUND_DASH = re.compile(r"(?<=[A-Za-z0-9])\s+-\s+(?=[A-Za-z0-9])")


def apply_commands(text: str, *, command_mode: bool = False) -> str:
    if not text:
        return ""
    protected = _PERIOD_OF.sub(_PERIOD_GUARD, text)
    phrases = _COMMAND_PHRASE_RES if command_mode else _PHRASE_RES
    for pattern, replacement in phrases:
        protected = pattern.sub(lambda _match, r=replacement: r, protected)
    protected = protected.replace(_PERIOD_GUARD, "period")
    return _glue_urls_and_punct(protected)


def _glue_urls_and_punct(text: str) -> str:
    text = _WWW_DOT.sub("www.", text)
    text = _DOMAIN_DOT.sub(r"\1", text)
    text = _SLASH_BETWEEN.sub("/", text)
    text = _SPACE_AROUND_DASH.sub("-", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = _SPACE_BEFORE_CLOSE.sub(r"\1", text)
    text = _SPACE_AROUND_NEWLINES.sub(r"\1", text)
    return text
