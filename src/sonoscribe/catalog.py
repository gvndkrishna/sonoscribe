"""Voice command library: load, validate, match aliases and slots."""

from __future__ import annotations

import copy
import json
import os
import re
import threading
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
from sonoscribe.apps import app_scope_ids, clean_apps, item_on_apps, scopes_overlap
from sonoscribe.device import clean_device_ids, iso_now, item_on_device, this_device_id
from sonoscribe.keys import clean_keys
from sonoscribe.scripts import RUNTIMES, looks_like_bundle_id, runtime_for_path
from sonoscribe.slots import (
    clean_pattern,
    conflict_key,
    has_slots,
    match_pattern,
    normalize_template,
    pattern_score,
    template_slot_keys,
    valid_variable_name,
    validate_pattern,
    variable_map,
)

COMMAND_TYPES = ("keyboard", "website", "app", "file", "system", "script", "text")
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
    bindings: dict[str, str] = field(default_factory=dict)


class ConfirmRequired(Exception):
    """Step-up re-auth is required before changing secret items."""


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
    return copy.deepcopy({"commands": DEFAULT_COMMANDS, "routines": [], "variables": []})


@dataclass
class _PhraseIndex:
    commands_by_phrase: dict[str, list[dict[str, Any]]]
    slotted_commands: list[tuple[str, dict[str, Any]]]
    routines_by_alias: dict[str, dict[str, Any]]
    slotted_routines: list[tuple[str, dict[str, Any]]]
    commands_by_id: dict[str, dict[str, Any]]


@dataclass
class _FileCache:
    resolved: Path
    mtime_ns: int
    size: int
    library: dict[str, Any]
    index: _PhraseIndex


_lock = threading.Lock()
_file_cache: _FileCache | None = None
_scratch_library: dict[str, Any] | None = None
_scratch_index: _PhraseIndex | None = None


def clear_library_cache() -> None:
    """Drop cached library and phrase maps. Tests and rare external writes."""
    global _file_cache, _scratch_library, _scratch_index
    with _lock:
        _file_cache = None
        _scratch_library = None
        _scratch_index = None


def _file_stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _build_index(library: dict[str, Any]) -> _PhraseIndex:
    commands_by_phrase: dict[str, list[dict[str, Any]]] = {}
    slotted_commands: list[tuple[str, dict[str, Any]]] = []
    commands_by_id: dict[str, dict[str, Any]] = {}
    routines_by_alias: dict[str, dict[str, Any]] = {}
    slotted_routines: list[tuple[str, dict[str, Any]]] = []
    for command in library.get("commands") or []:
        if not isinstance(command, dict):
            continue
        cmd_id = str(command.get("id") or "")
        if cmd_id:
            commands_by_id[cmd_id] = command
        for alias in command.get("phrases") or []:
            phrase = str(alias)
            if not phrase:
                continue
            if has_slots(phrase):
                slotted_commands.append((phrase, command))
            else:
                commands_by_phrase.setdefault(phrase, []).append(command)
    for routine in library.get("routines") or []:
        if not isinstance(routine, dict):
            continue
        for alias in _routine_aliases(routine):
            if has_slots(alias):
                slotted_routines.append((alias, routine))
            elif alias not in routines_by_alias:
                routines_by_alias[alias] = routine
    return _PhraseIndex(
        commands_by_phrase=commands_by_phrase,
        slotted_commands=slotted_commands,
        routines_by_alias=routines_by_alias,
        slotted_routines=slotted_routines,
        commands_by_id=commands_by_id,
    )


def _index_for(library: dict[str, Any]) -> _PhraseIndex:
    global _scratch_library, _scratch_index
    cache = _file_cache
    if cache is not None and library is cache.library:
        return cache.index
    if _scratch_library is library and _scratch_index is not None:
        return _scratch_index
    _scratch_library = library
    _scratch_index = _build_index(library)
    return _scratch_index


def _store_file_cache(resolved: Path, stamp: tuple[int, int], library: dict[str, Any]) -> None:
    global _file_cache
    _file_cache = _FileCache(
        resolved=resolved,
        mtime_ns=stamp[0],
        size=stamp[1],
        library=library,
        index=_build_index(library),
    )


def command_by_id(library: dict[str, Any], command_id: str) -> dict[str, Any] | None:
    with _lock:
        return _index_for(library).commands_by_id.get(command_id)


def match_utterance(
    text: str,
    library: dict[str, Any],
    device_id: str | None = None,
    frontmost: dict[str, str] | None = None,
) -> Match:
    phrase = normalize_phrase(text)
    if not phrase:
        return Match("unknown", label=text.strip())
    if device_id is None:
        device_id = this_device_id()
    tokens = phrase.split()
    variables = variable_map(library)
    with _lock:
        index = _index_for(library)
    if tokens[0] == RESERVED_PREFIX:
        if len(tokens) == 1:
            return Match("routine_incomplete", label="routine")
        rest = tokens[1:]
        name = " ".join(rest)
        routine = index.routines_by_alias.get(name)
        bindings: dict[str, str] = {}
        if routine is None:
            routine, bindings = _pick_slotted(index.slotted_routines, rest, variables, device_id)
        if routine is not None and (not device_id or item_on_device(routine, device_id)):
            label = str(routine.get("name") or name)
            return Match("routine", routine=routine, label=label, bindings=bindings)
        return Match("unknown", label=phrase)
    candidates = [
        item
        for item in (index.commands_by_phrase.get(phrase) or [])
        if not device_id or item_on_device(item, device_id)
    ]
    command = _pick_command(candidates, frontmost)
    if command is not None:
        label = str(command.get("name") or phrase)
        return Match("command", command=command, label=label)
    command, bindings = _pick_slotted(
        index.slotted_commands,
        tokens,
        variables,
        device_id,
        frontmost=frontmost,
    )
    if command is not None:
        label = str(command.get("name") or phrase)
        return Match("command", command=command, label=label, bindings=bindings)
    return Match("unknown", label=phrase)


def _pick_command(
    candidates: list[dict[str, Any]],
    frontmost: dict[str, str] | None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    scoped = [item for item in candidates if app_scope_ids(item)]
    globals_ = [item for item in candidates if not app_scope_ids(item)]
    snapped = bool(
        frontmost
        and (str(frontmost.get("bundle_id") or "").strip() or str(frontmost.get("name") or "").strip())
    )
    if snapped:
        hits = [item for item in scoped if item_on_apps(item, frontmost)]
        if hits:
            return hits[0]
        if globals_:
            return globals_[0]
        return None
    if globals_:
        return globals_[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _pick_slotted(
    items: list[tuple[str, dict[str, Any]]],
    tokens: list[str],
    variables: dict[str, str],
    device_id: str | None,
    frontmost: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    scored: list[tuple[tuple[int, int, int], dict[str, Any], dict[str, str]]] = []
    for pattern, item in items:
        if device_id and not item_on_device(item, device_id):
            continue
        bound = match_pattern(pattern, tokens, variables)
        if bound is None:
            continue
        scored.append((pattern_score(pattern), item, bound))
    if not scored:
        return None, {}
    scored.sort(key=lambda row: row[0], reverse=True)
    best = scored[0][0]
    top = [row for row in scored if row[0] == best]
    picked = _pick_command([row[1] for row in top], frontmost)
    if picked is None:
        return None, {}
    for _score, item, bound in top:
        if item is picked or item.get("id") == picked.get("id"):
            return picked, bound
    return picked, top[0][2]


def _routine_aliases(routine: dict[str, Any]) -> set[str]:
    names = {str(routine.get("name") or "").strip()}
    for alias in routine.get("phrases") or []:
        names.add(str(alias).strip())
    names.discard("")
    return names


def validate_library(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LibraryError(["Library must be an object"])
    errors: list[str] = []
    raw_commands = data.get("commands")
    raw_routines = data.get("routines")
    raw_variables = data.get("variables")
    if raw_commands is None:
        raw_commands = []
    if raw_routines is None:
        raw_routines = []
    if raw_variables is None:
        raw_variables = []
    if not isinstance(raw_commands, list):
        errors.append("commands must be a list")
        raw_commands = []
    if not isinstance(raw_routines, list):
        errors.append("routines must be a list")
        raw_routines = []
    if not isinstance(raw_variables, list):
        errors.append("variables must be a list")
        raw_variables = []

    variables: list[dict[str, Any]] = []
    seen_var_ids: set[str] = set()
    seen_var_names: set[str] = set()
    for index, raw in enumerate(raw_variables):
        prefix = f"Variable {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item, item_errors = _validate_variable(raw, prefix)
        errors.extend(item_errors)
        if item is None:
            continue
        if item["id"] in seen_var_ids:
            errors.append(f"{prefix}: duplicate id {item['id']!r}")
        seen_var_ids.add(item["id"])
        if item["name"] in seen_var_names:
            errors.append(f"{prefix}: duplicate name {item['name']!r}")
        seen_var_names.add(item["name"])
        variables.append(item)
    known_names = {item["name"] for item in variables}

    commands: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    phrase_owners: dict[str, list[tuple[str, frozenset[str]]]] = {}

    for index, raw in enumerate(raw_commands):
        prefix = f"Command {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item, item_errors = _validate_command(raw, prefix, known_names)
        errors.extend(item_errors)
        if item is None:
            continue
        if item["id"] in seen_ids:
            errors.append(f"{prefix}: duplicate id {item['id']!r}")
        seen_ids.add(item["id"])
        scope = app_scope_ids(item)
        for phrase in item["phrases"]:
            key = conflict_key(phrase)
            owners = phrase_owners.setdefault(key, [])
            conflict = next((name for name, other in owners if scopes_overlap(scope, other)), "")
            if conflict:
                errors.append(f"Phrase {phrase!r} is used by {conflict} and {item['name']}")
            else:
                owners.append((item["name"], scope))
        commands.append(item)

    routines: list[dict[str, Any]] = []
    seen_routine_ids: set[str] = set()
    routine_names: dict[str, str] = {}

    for index, raw in enumerate(raw_routines):
        prefix = f"Routine {index + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        item, item_errors = _validate_routine(raw, prefix, known_names)
        errors.extend(item_errors)
        if item is None:
            continue
        if item["id"] in seen_routine_ids:
            errors.append(f"{prefix}: duplicate id {item['id']!r}")
        seen_routine_ids.add(item["id"])
        for alias in _routine_aliases(item):
            key = conflict_key(alias)
            other = routine_names.get(key)
            if other:
                errors.append(f"Routine alias {alias!r} is used by {other} and {item['name']}")
            else:
                routine_names[key] = item["name"]
        routines.append(item)

    if errors:
        raise LibraryError(errors)
    return {"commands": commands, "routines": routines, "variables": variables}


def is_secret(item: dict[str, Any] | None) -> bool:
    return bool(item and item.get("secret"))


def skip_stats(item: dict[str, Any] | None, parent: dict[str, Any] | None = None) -> bool:
    return is_secret(item) or is_secret(parent)


def public_library(library: dict[str, Any]) -> dict[str, Any]:
    return {
        "commands": [item for item in library.get("commands") or [] if not is_secret(item)],
        "routines": [item for item in library.get("routines") or [] if not is_secret(item)],
        "variables": [item for item in library.get("variables") or [] if not is_secret(item)],
    }


def usable_library(library: dict[str, Any], *, lock_on: bool | None = None) -> dict[str, Any]:
    if lock_on is None:
        from sonoscribe.lock import lock_enabled

        lock_on = lock_enabled()
    if lock_on:
        return library
    return public_library(library)


def apply_library_update(
    current: dict[str, Any],
    incoming: Any,
    *,
    revealed: bool,
    confirmed: bool,
    lock_on: bool,
) -> dict[str, Any]:
    incoming = validate_library(incoming)
    current = validate_library(current) if current else empty_library()

    def merge(kind: str) -> list[dict[str, Any]]:
        cur_secret = [item for item in current.get(kind) or [] if is_secret(item)]
        in_all = incoming.get(kind) or []
        in_secret = [item for item in in_all if is_secret(item)]
        in_public = [item for item in in_all if not is_secret(item)]
        in_ids = {item["id"] for item in in_all}
        deleted = revealed and any(item["id"] not in in_ids for item in cur_secret)
        if in_secret and not lock_on:
            raise LibraryError(["Set a lock first."])
        if (in_secret or deleted) and not confirmed:
            raise ConfirmRequired("Confirm required.")
        if revealed:
            secrets = in_secret
        else:
            by_id = {item["id"]: item for item in cur_secret}
            for item in in_secret:
                by_id[item["id"]] = item
            secrets = list(by_id.values())
        secret_ids = {item["id"] for item in secrets}
        return [item for item in in_public if item["id"] not in secret_ids] + secrets

    return validate_library(
        {
            "commands": merge("commands"),
            "routines": merge("routines"),
            "variables": merge("variables"),
        }
    )


def _validate_variable(raw: dict[str, Any], prefix: str) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    name = str(raw.get("name") or "").strip().lower()
    if not valid_variable_name(name):
        errors.append(f"{prefix}: name must be a single word")
    var_id = str(raw.get("id") or "").strip() or new_id("var")
    value = str(raw.get("value") or "")
    if errors:
        return None, errors
    item: dict[str, Any] = {
        "id": var_id,
        "name": name,
        "value": value,
        "updated_at": str(raw.get("updated_at") or "") or iso_now(),
    }
    if bool(raw.get("secret")):
        item["secret"] = True
    return item, []


def _validate_command(
    raw: dict[str, Any],
    prefix: str,
    known_names: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    names = known_names or set()
    cmd_type = str(raw.get("type") or "").strip()
    if cmd_type not in COMMAND_TYPES:
        errors.append(f"{prefix}: type must be one of {', '.join(COMMAND_TYPES)}")
    name = str(raw.get("name") or "").strip()
    if not name:
        errors.append(f"{prefix}: name is required")
    cmd_id = str(raw.get("id") or "").strip() or new_id(cmd_type[:3] or "cmd")
    phrases, phrase_errors = _clean_phrases(raw.get("phrases"), prefix, known_names=names)
    errors.extend(phrase_errors)
    item: dict[str, Any] = {
        "id": cmd_id,
        "type": cmd_type,
        "name": name or "Untitled",
        "phrases": phrases,
        "devices": clean_device_ids(raw.get("devices")),
        "apps": clean_apps(raw.get("apps")),
        "updated_at": str(raw.get("updated_at") or "") or iso_now(),
    }
    if bool(raw.get("secret")):
        item["secret"] = True
    if cmd_type == "keyboard":
        action = str(raw.get("action") or "").strip()
        keys, key_errors = clean_keys(raw.get("keys"), prefix)
        errors.extend(key_errors)
        if keys:
            item["keys"] = keys
        elif action in KEYBOARD_ACTIONS:
            item["action"] = action
        else:
            errors.append(f"{prefix}: record keystrokes for this keyboard command")
    elif cmd_type == "website":
        url = normalize_template(str(raw.get("url") or "").strip())
        if not _valid_http_url(url):
            errors.append(f"{prefix}: url must be http or https")
        errors.extend(_template_errors(url, prefix, names))
        item["url"] = url
    elif cmd_type == "app":
        bundle_id = str(raw.get("bundle_id") or "").strip()
        app = normalize_template(str(raw.get("app") or "").strip())
        if has_slots(app) or has_slots(bundle_id):
            target = app or normalize_template(bundle_id)
            if not target:
                errors.append(f"{prefix}: app name or bundle id is required")
            errors.extend(_template_errors(target, prefix, names))
            item["app"] = target
        else:
            label = app if app and not looks_like_bundle_id(app) else ""
            if looks_like_bundle_id(bundle_id):
                item["bundle_id"] = bundle_id
            elif looks_like_bundle_id(app):
                item["bundle_id"] = app
            elif app:
                item["app"] = app
            elif bundle_id:
                item["app"] = bundle_id
            else:
                errors.append(f"{prefix}: app name or bundle id is required")
            if label and item.get("bundle_id"):
                item["app"] = label
    elif cmd_type == "file":
        path = normalize_template(str(raw.get("path") or "").strip())
        if not path:
            errors.append(f"{prefix}: path is required")
        errors.extend(_template_errors(path, prefix, names))
        item["path"] = path
    elif cmd_type == "system":
        action = str(raw.get("action") or "").strip()
        if action not in SYSTEM_ACTIONS:
            errors.append(f"{prefix}: system action must be one of {', '.join(SYSTEM_ACTIONS)}")
        item["action"] = action
    elif cmd_type == "script":
        runtime = str(raw.get("runtime") or "").strip()
        body = normalize_template(str(raw.get("body") or ""))
        path = normalize_template(str(raw.get("path") or "").strip())
        if path and runtime not in RUNTIMES:
            runtime = runtime_for_path(path)
        if runtime not in RUNTIMES:
            errors.append(f"{prefix}: script runtime must be bash or applescript")
        if not body.strip() and not path:
            errors.append(f"{prefix}: paste a script or choose a file")
        errors.extend(_template_errors(body, prefix, names))
        errors.extend(_template_errors(path, prefix, names))
        item["runtime"] = runtime or "bash"
        if body.strip():
            item["body"] = body
        if path:
            item["path"] = path
    elif cmd_type == "text":
        text = normalize_template(str(raw.get("text") or ""))
        errors.extend(_template_errors(text, prefix, names))
        item["text"] = text
    if errors:
        return None, errors
    return item, []


def _validate_routine(
    raw: dict[str, Any],
    prefix: str,
    known_names: set[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    names = known_names or set()
    raw_name = str(raw.get("name") or "").strip()
    name, name_errors = clean_pattern(raw_name)
    errors.extend(f"{prefix}: {err}" for err in name_errors)
    if not name:
        errors.append(f"{prefix}: name is required")
    else:
        if name.split()[0] == RESERVED_PREFIX:
            errors.append(f"{prefix}: name cannot start with {RESERVED_PREFIX!r}")
        errors.extend(f"{prefix}: {err}" for err in validate_pattern(name, names))
    rtn_id = str(raw.get("id") or "").strip() or new_id("rtn")
    phrases, phrase_errors = _clean_phrases(raw.get("phrases") or [], prefix, allow_empty=True, known_names=names)
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
    item: dict[str, Any] = {
        "id": rtn_id,
        "name": name,
        "phrases": phrases,
        "steps": steps,
        "devices": clean_device_ids(raw.get("devices")),
        "updated_at": str(raw.get("updated_at") or "") or iso_now(),
    }
    if bool(raw.get("secret")):
        item["secret"] = True
    return item, []


def _clean_phrases(
    raw: Any,
    prefix: str,
    allow_empty: bool = False,
    known_names: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    names = known_names or set()
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], [f"{prefix}: phrases must be a list"]
    phrases: list[str] = []
    seen: set[str] = set()
    for item in raw:
        phrase, phrase_errors = clean_pattern(str(item))
        errors.extend(f"{prefix}: {err}" for err in phrase_errors)
        if not phrase:
            continue
        if phrase.split()[0] == RESERVED_PREFIX:
            errors.append(f"{prefix}: phrase {phrase!r} cannot start with {RESERVED_PREFIX!r}")
            continue
        for err in validate_pattern(phrase, names):
            errors.append(f"{prefix}: phrase {phrase!r} {err}")
            phrase = ""
            break
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase)
    if not phrases and not allow_empty:
        errors.append(f"{prefix}: at least one phrase is required")
    return phrases, errors


def _template_errors(text: str, prefix: str, known_names: set[str]) -> list[str]:
    errors: list[str] = []
    for key in template_slot_keys(text):
        if key.isdigit() or key == "*":
            continue
        if key not in known_names:
            errors.append(f"{prefix}: unknown variable {{{key}}}")
    return errors


def _valid_http_url(url: str) -> bool:
    dummy = re.sub(r"\{[a-z0-9_*]+\}", "slot", url)
    parsed = urlparse(dummy)
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


def remap_device_id(old_id: str, new_id: str) -> bool:
    previous = str(old_id or "").strip()
    current = str(new_id or "").strip()
    if not previous or not current or previous == current:
        return False
    library = load_library()
    changed = False
    for key in ("commands", "routines"):
        for item in library.get(key) or []:
            assigned = item.get("devices")
            if not isinstance(assigned, list) or previous not in assigned:
                continue
            seen: set[str] = set()
            rewritten: list[str] = []
            for value in assigned:
                next_id = current if value == previous else str(value)
                if not next_id or next_id in seen:
                    continue
                seen.add(next_id)
                rewritten.append(next_id)
            item["devices"] = rewritten
            changed = True
    if changed:
        save_library(library)
    return changed


def load_library(path: Path | None = None) -> dict[str, Any]:
    target = (path or library_path()).resolve()
    with _lock:
        return _load_library_locked(target)


def _load_library_locked(target: Path) -> dict[str, Any]:
    stamp = _file_stamp(target)
    cache = _file_cache
    if (
        cache is not None
        and cache.resolved == target
        and stamp is not None
        and cache.mtime_ns == stamp[0]
        and cache.size == stamp[1]
    ):
        return cache.library

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            library = validate_library(data)
        except (OSError, json.JSONDecodeError, LibraryError):
            library = empty_library()
        fresh = _file_stamp(target) or stamp or (0, 0)
        _store_file_cache(target, fresh, library)
        return library

    github = _read_github_map(legacy_routines_path())
    library = empty_library()
    if github:
        websites = commands_from_github_map(github)
        if websites:
            seeded = [item for item in library["commands"] if item.get("type") != "website"]
            library = {"commands": seeded + websites, "routines": [], "variables": []}
    return _write_library_locked(library, target)


def save_library(library: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    cleaned = validate_library(library)
    target = (path or library_path()).resolve()
    with _lock:
        return _write_library_locked(cleaned, target)


def _write_library_locked(library: dict[str, Any], target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")
    stamp = _file_stamp(target) or (0, 0)
    _store_file_cache(target, stamp, library)
    return library
