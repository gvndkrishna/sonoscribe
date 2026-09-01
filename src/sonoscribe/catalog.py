"""Voice command library: load, validate, match exact aliases."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sonoscribe.actions import (
    BACKSPACE,
    DELETE_SENTENCE,
    DELETE_WORD,
    ENTER,
    SCRATCH,
    norm_token,
)

COMMAND_TYPES = ("keyboard", "website", "app", "file", "system")
KEYBOARD_ACTIONS = (ENTER, BACKSPACE, DELETE_WORD, DELETE_SENTENCE, SCRATCH)
SYSTEM_ACTIONS = (
    "mute",
    "unmute",
    "volume_up",
    "volume_down",
    "play_pause",
    "next",
    "previous",
    "lock",
    "sleep",
    "display_sleep",
    "screenshot",
    "screenshot_selection",
)
RESERVED_PREFIX = "routine"
_ENV_LIBRARY = "SONOSCRIBE_LIBRARY"
_ANDROID_URL = "https://github.com/SquareX-Backup/sqx-core-android"

DEFAULT_COMMANDS: list[dict[str, Any]] = [
    {
        "id": "kbd-enter",
        "type": "keyboard",
        "name": "Enter",
        "phrases": ["enter"],
        "action": ENTER,
    },
    {
        "id": "kbd-backspace",
        "type": "keyboard",
        "name": "Backspace",
        "phrases": ["backspace"],
        "action": BACKSPACE,
    },
    {
        "id": "kbd-delete-word",
        "type": "keyboard",
        "name": "Delete last word",
        "phrases": [
            "delete last word",
            "delete the last word",
            "scratch last word",
            "backspace word",
            "delete word",
        ],
        "action": DELETE_WORD,
    },
    {
        "id": "kbd-delete-sentence",
        "type": "keyboard",
        "name": "Delete last sentence",
        "phrases": [
            "delete last sentence",
            "delete the last sentence",
            "scratch last sentence",
        ],
        "action": DELETE_SENTENCE,
    },
    {
        "id": "kbd-scratch",
        "type": "keyboard",
        "name": "Scratch that",
        "phrases": ["scratch that", "undo that", "delete that"],
        "action": SCRATCH,
    },
    {
        "id": "web-android",
        "type": "website",
        "name": "Android repo",
        "phrases": ["android", "github android", "git hub android"],
        "url": _ANDROID_URL,
    },
]


@dataclass(frozen=True)
class Match:
    kind: str  # command | routine | routine_incomplete | unknown
    command: dict[str, Any] | None = None
    routine: dict[str, Any] | None = None
    label: str = ""


@dataclass
class LibraryError(ValueError):
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "; ".join(self.errors) if self.errors else "Invalid library"


def support_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Sonoscribe"


def library_path() -> Path:
    override = os.environ.get(_ENV_LIBRARY)
    if override:
        return Path(override)
    return support_dir() / "library.json"


def legacy_routines_path() -> Path:
    override = os.environ.get("SONOSCRIBE_ROUTINES")
    if override:
        return Path(override)
    return support_dir() / "routines.json"


def new_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def normalize_phrase(text: str) -> str:
    parts = [norm_token(p) for p in re.split(r"\s+", text.strip())]
    return " ".join(p for p in parts if p)


def empty_library() -> dict[str, Any]:
    return copy.deepcopy({"commands": DEFAULT_COMMANDS, "routines": []})


def command_by_id(library: dict[str, Any], command_id: str) -> dict[str, Any] | None:
    for item in library.get("commands") or []:
        if isinstance(item, dict) and item.get("id") == command_id:
            return item
    return None


def match_utterance(text: str, library: dict[str, Any]) -> Match:
    phrase = normalize_phrase(text)
    if not phrase:
        return Match("unknown", label=text.strip())
    tokens = phrase.split()
    if tokens[0] == RESERVED_PREFIX:
        if len(tokens) == 1:
            return Match("routine_incomplete", label="routine")
        name = " ".join(tokens[1:])
        for routine in library.get("routines") or []:
            if not isinstance(routine, dict):
                continue
            aliases = _routine_aliases(routine)
            if name in aliases:
                label = str(routine.get("name") or name)
                return Match("routine", routine=routine, label=label)
        return Match("unknown", label=phrase)
    for command in library.get("commands") or []:
        if not isinstance(command, dict):
            continue
        for alias in command.get("phrases") or []:
            if normalize_phrase(str(alias)) == phrase:
                label = str(command.get("name") or phrase)
                return Match("command", command=command, label=label)
    return Match("unknown", label=phrase)


def _routine_aliases(routine: dict[str, Any]) -> set[str]:
    names = {normalize_phrase(str(routine.get("name") or ""))}
    for alias in routine.get("phrases") or []:
        names.add(normalize_phrase(str(alias)))
    names.discard("")
    return names


def validate_library(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LibraryError(["Library must be an object"])
    errors: list[str] = []
    raw_commands = data.get("commands")
    raw_routines = data.get("routines")
    if raw_commands is None:
        raw_commands = []
    if raw_routines is None:
        raw_routines = []
    if not isinstance(raw_commands, list):
        errors.append("commands must be a list")
        raw_commands = []
    if not isinstance(raw_routines, list):
        errors.append("routines must be a list")
        raw_routines = []

    commands: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    phrase_owner: dict[str, str] = {}

    for index, raw in enumerate(raw_commands):
        prefix = f"Command {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item, item_errors = _validate_command(raw, prefix)
        errors.extend(item_errors)
        if item is None:
            continue
        if item["id"] in seen_ids:
            errors.append(f"{prefix}: duplicate id {item['id']!r}")
        seen_ids.add(item["id"])
        for phrase in item["phrases"]:
            other = phrase_owner.get(phrase)
            if other:
                errors.append(f"Phrase {phrase!r} is used by {other} and {item['name']}")
            else:
                phrase_owner[phrase] = item["name"]
        commands.append(item)

    routines: list[dict[str, Any]] = []
    seen_routine_ids: set[str] = set()
    routine_names: dict[str, str] = {}

    for index, raw in enumerate(raw_routines):
        prefix = f"Routine {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item, item_errors = _validate_routine(raw, prefix)
        errors.extend(item_errors)
        if item is None:
            continue
        if item["id"] in seen_routine_ids:
            errors.append(f"{prefix}: duplicate id {item['id']!r}")
        seen_routine_ids.add(item["id"])
        for alias in _routine_aliases(item):
            other = routine_names.get(alias)
            if other:
                errors.append(f"Routine alias {alias!r} is used by {other} and {item['name']}")
            else:
                routine_names[alias] = item["name"]
        routines.append(item)

    if errors:
        raise LibraryError(errors)
    return {"commands": commands, "routines": routines}


def _validate_command(raw: dict[str, Any], prefix: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    cmd_type = str(raw.get("type") or "").strip()
    if cmd_type not in COMMAND_TYPES:
        errors.append(f"{prefix}: type must be one of {', '.join(COMMAND_TYPES)}")
    name = str(raw.get("name") or "").strip()
    if not name:
        errors.append(f"{prefix}: name is required")
    cmd_id = str(raw.get("id") or "").strip() or new_id(cmd_type[:3] or "cmd")
    phrases, phrase_errors = _clean_phrases(raw.get("phrases"), prefix)
    errors.extend(phrase_errors)
    item: dict[str, Any] = {
        "id": cmd_id,
        "type": cmd_type,
        "name": name or "Untitled",
        "phrases": phrases,
    }
    if cmd_type == "keyboard":
        action = str(raw.get("action") or "").strip()
        if action not in KEYBOARD_ACTIONS:
            errors.append(f"{prefix}: keyboard action must be one of {', '.join(KEYBOARD_ACTIONS)}")
        item["action"] = action
    elif cmd_type == "website":
        url = str(raw.get("url") or "").strip()
        if not _valid_http_url(url):
            errors.append(f"{prefix}: url must be http or https")
        item["url"] = url
    elif cmd_type == "app":
        app = str(raw.get("app") or "").strip()
        if not app:
            errors.append(f"{prefix}: app name is required")
        item["app"] = app
    elif cmd_type == "file":
        path = str(raw.get("path") or "").strip()
        if not path:
            errors.append(f"{prefix}: path is required")
        item["path"] = path
    elif cmd_type == "system":
        action = str(raw.get("action") or "").strip()
        if action not in SYSTEM_ACTIONS:
            errors.append(f"{prefix}: system action must be one of {', '.join(SYSTEM_ACTIONS)}")
        item["action"] = action
    if errors:
        return None, errors
    return item, []


def _validate_routine(
    raw: dict[str, Any],
    prefix: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    name = str(raw.get("name") or "").strip()
    if not name:
        errors.append(f"{prefix}: name is required")
    elif normalize_phrase(name).startswith(RESERVED_PREFIX):
        errors.append(f"{prefix}: name cannot start with {RESERVED_PREFIX!r}")
    rtn_id = str(raw.get("id") or "").strip() or new_id("rtn")
    phrases, phrase_errors = _clean_phrases(raw.get("phrases") or [], prefix, allow_empty=True)
    errors.extend(phrase_errors)
    steps: list[dict[str, Any]] = []
    raw_steps = raw.get("steps") or []
    if not isinstance(raw_steps, list):
        errors.append(f"{prefix}: steps must be a list")
        raw_steps = []
    for step_index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            errors.append(f"{prefix} step {step_index + 1} must be an object")
            continue
        command_id = str(raw_step.get("command_id") or "").strip()
        if not command_id:
            errors.append(f"{prefix} step {step_index + 1}: command_id is required")
            continue
        try:
            delay_ms = int(raw_step.get("delay_ms") or 0)
        except (TypeError, ValueError):
            errors.append(f"{prefix} step {step_index + 1}: delay_ms must be an integer")
            delay_ms = 0
        if delay_ms < 0:
            errors.append(f"{prefix} step {step_index + 1}: delay_ms cannot be negative")
        steps.append({"command_id": command_id, "delay_ms": max(0, delay_ms)})
    if errors:
        return None, errors
    return {"id": rtn_id, "name": name, "phrases": phrases, "steps": steps}, []


def _clean_phrases(raw: Any, prefix: str, allow_empty: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], [f"{prefix}: phrases must be a list"]
    phrases: list[str] = []
    seen: set[str] = set()
    for item in raw:
        phrase = normalize_phrase(str(item))
        if not phrase:
            continue
        if phrase.split()[0] == RESERVED_PREFIX:
            errors.append(f"{prefix}: phrase {phrase!r} cannot start with {RESERVED_PREFIX!r}")
            continue
        if phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
    if not phrases and not allow_empty:
        errors.append(f"{prefix}: at least one phrase is required")
    return phrases, errors


def _valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def commands_from_github_map(github: dict[str, str]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for raw_alias, raw_url in github.items():
        alias = normalize_phrase(str(raw_alias))
        url = str(raw_url).strip()
        if not alias or not _valid_http_url(url):
            continue
        slug = alias.replace(" ", "-")
        phrases = [alias, f"github {alias}", f"git hub {alias}"]
        unique: list[str] = []
        for phrase in phrases:
            if phrase not in unique:
                unique.append(phrase)
        name = "Android repo" if alias == "android" else alias.title()
        commands.append(
            {
                "id": f"web-{slug}",
                "type": "website",
                "name": name,
                "phrases": unique,
                "url": url,
            }
        )
    return commands


def _read_github_map(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    github = data.get("github")
    if not isinstance(github, dict):
        return None
    out: dict[str, str] = {}
    for key, value in github.items():
        alias = str(key).strip().lower()
        url = str(value).strip()
        if alias and url:
            out[alias] = url
    return out


def load_library(path: Path | None = None) -> dict[str, Any]:
    target = path or library_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            return validate_library(data)
        except (OSError, json.JSONDecodeError, LibraryError):
            return empty_library()

    github = _read_github_map(legacy_routines_path())
    library = empty_library()
    if github:
        websites = commands_from_github_map(github)
        if websites:
            seeded = [item for item in library["commands"] if item.get("type") != "website"]
            library = {"commands": seeded + websites, "routines": []}
    save_library(library, target)
    return library


def save_library(library: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    cleaned = validate_library(library)
    target = path or library_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
    return cleaned
