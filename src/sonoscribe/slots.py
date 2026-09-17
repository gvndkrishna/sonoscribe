"""Capture slots and named voice-variable expansion."""

from __future__ import annotations

import re
from typing import Any

from sonoscribe.actions import norm_token

RESERVED_NAME = "routine"
_SLOT_TOKEN = re.compile(r"^\{([^{}]+)\}$")
_SLOT_IN_TEXT = re.compile(r"\{([a-z0-9_*]+)\}")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_slot(token: str) -> tuple[str, str] | None:
    match = _SLOT_TOKEN.fullmatch(str(token or "").strip())
    if not match:
        return None
    name = match.group(1).strip().lower()
    if name == "*":
        return ("rest", "*")
    if name.isdigit() and int(name) >= 1:
        return ("capture", str(int(name)))
    if _NAME_RE.fullmatch(name) and name != RESERVED_NAME:
        return ("name", name)
    return None


def is_slot_token(token: str) -> bool:
    return parse_slot(token) is not None


def has_slots(text: str) -> bool:
    return bool(pattern_slot_keys(text) or template_slot_keys(text))


def pattern_slot_keys(pattern: str) -> set[str]:
    keys: set[str] = set()
    for part in str(pattern or "").split():
        slot = parse_slot(part)
        if slot:
            keys.add(slot[1])
    return keys


def template_slot_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for match in _SLOT_IN_TEXT.finditer(str(text or "")):
        slot = parse_slot("{" + match.group(1) + "}")
        if slot:
            keys.add(slot[1])
    return keys


def conflict_key(pattern: str) -> str:
    parts: list[str] = []
    for part in str(pattern or "").split():
        slot = parse_slot(part)
        if slot is None:
            parts.append(part)
        elif slot[0] == "capture":
            parts.append("{#}")
        else:
            parts.append(f"{{{slot[1]}}}")
    return " ".join(parts)


def pattern_score(pattern: str) -> tuple[int, int, int]:
    literals = 0
    named = 0
    star = 0
    for part in str(pattern or "").split():
        slot = parse_slot(part)
        if slot is None:
            literals += 1
        elif slot[0] == "name":
            named += 1
        elif slot[0] == "rest":
            star = 1
    return (literals, 1 - star, named)


def clean_pattern(text: str) -> tuple[str, list[str]]:
    errors: list[str] = []
    parts: list[str] = []
    for raw in re.split(r"\s+", str(text or "").strip()):
        if not raw:
            continue
        if "{" in raw or "}" in raw:
            inner = _SLOT_TOKEN.fullmatch(raw)
            if not inner:
                errors.append(f"invalid slot {raw!r}")
                continue
            name = inner.group(1).strip().lower()
            token = f"{{{name}}}"
            slot = parse_slot(token)
            if slot is None:
                errors.append(f"invalid slot {raw!r}")
                continue
            parts.append(f"{{{slot[1]}}}")
            continue
        token = norm_token(raw)
        if token:
            parts.append(token)
    return " ".join(parts), errors


def validate_pattern(pattern: str, known_names: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    parts = str(pattern or "").split()
    if not parts:
        return errors
    names = known_names or set()
    if parse_slot(parts[0]):
        errors.append("cannot start with a variable")
    for index, part in enumerate(parts):
        slot = parse_slot(part)
        if slot is None:
            continue
        kind, name = slot
        if kind == "rest" and index != len(parts) - 1:
            errors.append("{*} must be last")
        if kind == "name" and name not in names:
            errors.append(f"unknown variable {{{name}}}")
    return errors


def match_pattern(
    pattern: str,
    tokens: list[str],
    variables: dict[str, str] | None = None,
) -> dict[str, str] | None:
    parts = str(pattern or "").split()
    if not parts:
        return None
    names = variables or {}
    spoken = list(tokens)
    bindings: dict[str, str] = {}
    cursor = 0
    for index, part in enumerate(parts):
        slot = parse_slot(part)
        if slot is None:
            if cursor >= len(spoken) or spoken[cursor] != part:
                return None
            cursor += 1
            continue
        kind, name = slot
        if kind == "rest":
            if index != len(parts) - 1:
                return None
            bindings["*"] = " ".join(spoken[cursor:])
            cursor = len(spoken)
            continue
        if cursor >= len(spoken):
            return None
        word = spoken[cursor]
        cursor += 1
        if kind == "capture":
            bindings[name] = word
        elif name not in names or word != name:
            return None
        else:
            bindings[name] = names[name]
    if cursor != len(spoken):
        return None
    return bindings


def normalize_template(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        slot = parse_slot("{" + match.group(1).strip().lower() + "}")
        if slot is None:
            return match.group(0)
        return "{" + slot[1] + "}"

    return _SLOT_IN_TEXT.sub(repl, str(text or ""))


def fill(template: str, bindings: dict[str, str] | None = None, variables: dict[str, str] | None = None) -> str:
    bound = bindings or {}
    names = variables or {}

    def repl(match: re.Match[str]) -> str:
        slot = parse_slot("{" + match.group(1) + "}")
        if slot is None:
            return ""
        kind, name = slot
        if kind == "rest":
            return expand_star(bound.get("*", ""), names)
        if kind == "capture":
            return bound.get(name, "")
        if name in bound:
            return bound[name]
        return names.get(name, "")

    return _SLOT_IN_TEXT.sub(repl, str(template or ""))


def expand_star(text: str, variables: dict[str, str] | None = None) -> str:
    names = variables or {}
    parts = [part for part in str(text or "").split() if part]
    return " ".join(names.get(part, part) for part in parts)


def variable_map(library: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in (library or {}).get("variables") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            out[name] = str(item.get("value") or "")
    return out


def valid_variable_name(name: str) -> bool:
    return bool(_NAME_RE.fullmatch(name) and name != RESERVED_NAME)
