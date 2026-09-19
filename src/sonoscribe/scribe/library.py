"""Scout library tool: list/get/upsert/delete commands, routines, vocab, vocanotes."""

from __future__ import annotations

import json
import re
from typing import Any

from sonoscribe.catalog import LibraryError, is_secret, load_library, public_library, save_library
from sonoscribe.device import iso_now
from sonoscribe.scribe.parse import next_clock, parse_scribe, wants_scribe_save
from sonoscribe.scribe.store import delete_vocanotes, get_vocanote, list_vocanotes, upsert_vocanote

_KIND = {
    "command": "commands",
    "commands": "commands",
    "routine": "routines",
    "routines": "routines",
    "vocab": "variables",
    "variable": "variables",
    "variables": "variables",
    "vocanote": "vocanotes",
    "note": "vocanotes",
    "notes": "vocanotes",
    "scribe": "vocanotes",
}
_LABEL = {
    "commands": "command",
    "routines": "routine",
    "variables": "vocab",
    "vocanotes": "vocanote",
}
_LIMIT = 20

LIBRARY_SPEC = {
    "name": "library",
    "description": (
        "Add, change, fetch, or delete a Sonoscribe command, routine, vocab item, or vocanote. "
        "A vocanote is always a note and may also be a to-do and/or a reminder. "
        "A title that starts with a verb is a to-do. "
        "If they name a clock without am or pm, due_at is the next that hour AM or PM. "
        "A calendar date (December 18, 2026) is that day at 8:00 if they named no clock. "
        "Monday, next Monday, weekend, and next week set due_at. "
        "daily, everyday, every friday, weekdays, and weekends set repeat. "
        "If they asked to add or save a reminder, you must upsert a vocanote. "
        "Reminders fire once unless repeat is set. Do not touch secret items."
    ),
    "schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get", "upsert", "delete"]},
            "kind": {"type": "string", "enum": ["command", "routine", "vocab", "vocanote"]},
            "id": {"type": "string"},
            "query": {"type": "string"},
            "item": {"type": "object"},
        },
        "required": ["action", "kind"],
    },
}


def library_tool_specs() -> list[dict[str, Any]]:
    return [dict(LIBRARY_SPEC)]


def normalize_kind(raw: Any) -> str:
    return _KIND.get(str(raw or "").strip().lower(), "")


def library_write_needs_confirm(args: dict[str, Any] | None) -> bool:
    data = args if isinstance(args, dict) else {}
    action = str(data.get("action") or "").strip().lower()
    kind = normalize_kind(data.get("kind"))
    if action in {"list", "get", ""}:
        return False
    if action in {"upsert", "delete"} and kind == "vocanotes":
        return False
    return action in {"upsert", "delete"}


def save_scribe_from_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    data = run if isinstance(run, dict) else {}
    ask = " ".join(part for part in (str(data.get("prompt") or ""), str(data.get("follow_up") or "")) if part)
    if not wants_scribe_save(ask) or _library_saved_vocanote(data):
        return None
    title, body, blob = _scribe_bits_from_answer(data.get("answer"), ask)
    if not title:
        return None
    parsed = parse_scribe(" ".join(part for part in (title, body, blob) if part))
    due = str(parsed.get("due_at") or "")
    if not due:
        due = next_clock(8).isoformat(timespec="seconds")
    return upsert_vocanote(
        {
            "title": title,
            "body": body,
            "is_todo": bool(parsed.get("is_todo")),
            "is_reminder": True,
            "due_at": due,
            "repeat": parsed.get("repeat") or "",
        }
    )


def _library_saved_vocanote(run: dict[str, Any]) -> bool:
    for step in run.get("steps") or []:
        if not isinstance(step, dict) or step.get("name") != "library":
            continue
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        if str(args.get("action") or "").strip().lower() != "upsert":
            continue
        if normalize_kind(args.get("kind")) != "vocanotes":
            continue
        return True
    return False


def _scribe_bits_from_answer(answer: Any, fallback: str) -> tuple[str, str, str]:
    data = answer if isinstance(answer, dict) else {}
    facts: list[str] = []
    lead = ""
    named = ""
    for block in data.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type") or "")
        if kind == "lead" and not lead:
            lead = str(block.get("text") or "").strip()
        if kind != "facts":
            continue
        for row in block.get("rows") or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            label = str(row[0] or "").strip()
            value = str(row[1] or "").strip()
            if value:
                facts.append(value)
            if value and label.casefold() in {"movie", "title", "show", "event", "name", "film"}:
                named = value
    title = named or str(data.get("title") or "").strip()
    title = re.sub(r"(?i)\s+added$", "", title).strip()
    if not title:
        title = " ".join(str(fallback or "").split())[:80]
    return title[:200], lead[:8000], " ".join(facts)


def run_library(args: dict[str, Any] | None) -> str:
    data = args if isinstance(args, dict) else {}
    action = str(data.get("action") or "").strip().lower()
    kind = normalize_kind(data.get("kind"))
    if action not in {"list", "get", "upsert", "delete"}:
        raise _error("library action must be list, get, upsert, or delete.")
    if not kind:
        raise _error("library kind must be command, routine, vocab, or vocanote.")
    if action == "list":
        return _list(kind, str(data.get("query") or ""))
    if action == "get":
        return _get(kind, str(data.get("id") or ""))
    if action == "delete":
        return _delete(kind, str(data.get("id") or ""))
    item = data.get("item") if isinstance(data.get("item"), dict) else {}
    return _upsert(kind, item, str(data.get("id") or ""))


def compact_library_context(limit: int = _LIMIT) -> str:
    library = public_library(load_library())
    lines = [
        "Sonoscribe library (library tool; no secrets). Vocanotes: always a note; set is_todo / is_reminder. "
        "Clock without am/pm → next that hour AM or PM. Monday / next Monday / weekend / next week set a day. "
        "daily or every friday sets repeat. A named date is that day at 8:00."
    ]
    for key, label in (("commands", "commands"), ("routines", "routines"), ("variables", "vocab"), ("vocanotes", "vocanotes")):
        items = [item for item in (library.get(key) or []) if isinstance(item, dict)]
        if key == "vocanotes":
            items = list_vocanotes(library, secrets=False)
        lines.append(f"{label} ({len(items)}):")
        for item in items[:limit]:
            if key == "vocanotes":
                flags = []
                if item.get("is_todo"):
                    flags.append("todo")
                if item.get("is_reminder"):
                    flags.append(f"reminder {item.get('due_at') or ''}".strip())
                if item.get("repeat"):
                    flags.append(str(item.get("repeat")))
                extra = f" · {' · '.join(flags)}" if flags else ""
                lines.append(f"  {item.get('id')}  {item.get('title')}{extra}")
            else:
                lines.append(f"  {item.get('id')}  {item.get('name')}")
        if len(items) > limit:
            lines.append(f"  … {len(items) - limit} more")
    return "\n".join(lines)


def _list(kind: str, query: str) -> str:
    needle = query.strip().casefold()
    rows = []
    for item in _public_items(kind):
        blob = json.dumps(item, ensure_ascii=False).casefold()
        if needle and needle not in blob:
            continue
        rows.append(_brief(kind, item))
        if len(rows) >= 40:
            break
    if not rows:
        return f"no {_LABEL[kind]}s"
    return json.dumps(rows, ensure_ascii=False)


def _get(kind: str, ident: str) -> str:
    item = _find(kind, ident)
    if item is None:
        raise _error(f"{_LABEL[kind]} not found.")
    return json.dumps(item, ensure_ascii=False)


def _delete(kind: str, ident: str) -> str:
    wanted = ident.strip()
    if not wanted:
        raise _error("id is required.")
    if kind == "vocanotes":
        delete_vocanotes([wanted])
        return f"deleted vocanote {wanted}"
    library = load_library()
    items = [item for item in (library.get(kind) or []) if isinstance(item, dict)]
    if not any(item.get("id") == wanted for item in items):
        raise _error(f"{_LABEL[kind]} not found.")
    if any(item.get("id") == wanted and is_secret(item) for item in items):
        raise _error("secret items stay untouched.")
    library[kind] = [item for item in items if item.get("id") != wanted]
    if kind == "commands":
        routines = []
        for routine in library.get("routines") or []:
            if not isinstance(routine, dict):
                continue
            steps = [step for step in (routine.get("steps") or []) if str(step.get("command_id") or "") != wanted]
            routines.append({**routine, "steps": steps})
        library["routines"] = routines
    save_library(library)
    return f"deleted {_LABEL[kind]} {wanted}"


def _upsert(kind: str, item: dict[str, Any], ident: str) -> str:
    payload = dict(item)
    if ident and not payload.get("id"):
        payload["id"] = ident
    if kind == "vocanotes":
        title = str(payload.get("title") or payload.get("text") or payload.get("note") or "").strip()
        saved = upsert_vocanote(payload, parse_text=title or None)
        return json.dumps(saved, ensure_ascii=False)
    library = load_library()
    items = [entry for entry in (library.get(kind) or []) if isinstance(entry, dict)]
    existing = None
    index = -1
    found = str(payload.get("id") or "").strip()
    if found:
        for pos, entry in enumerate(items):
            if entry.get("id") == found:
                existing = entry
                index = pos
                break
    if existing is not None and is_secret(existing):
        raise _error("secret items stay untouched.")
    if existing is not None and payload.get("secret"):
        raise _error("secret items stay untouched.")
    merged = {**(existing or {}), **payload}
    if existing is not None:
        merged["id"] = existing["id"]
    merged["updated_at"] = iso_now()
    if index >= 0:
        items[index] = merged
    else:
        items.append(merged)
    library[kind] = items
    try:
        saved = save_library(library)
    except LibraryError as exc:
        raise _error(str(exc)) from exc
    out = _find(kind, str(merged.get("id") or ""), saved)
    return json.dumps(out or _brief(kind, merged), ensure_ascii=False)


def _public_items(kind: str) -> list[dict[str, Any]]:
    if kind == "vocanotes":
        return list_vocanotes(secrets=False)
    library = public_library(load_library())
    return [item for item in (library.get(kind) or []) if isinstance(item, dict)]


def _find(kind: str, ident: str, library: dict[str, Any] | None = None) -> dict[str, Any] | None:
    wanted = ident.strip()
    if not wanted:
        return None
    if kind == "vocanotes":
        return get_vocanote(wanted, library)
    source = public_library(library) if library is not None else public_library(load_library())
    for item in source.get(kind) or []:
        if isinstance(item, dict) and item.get("id") == wanted:
            return item
    return None


def _brief(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    if kind == "vocanotes":
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "is_todo": bool(item.get("is_todo")),
            "is_reminder": bool(item.get("is_reminder")),
            "due_at": item.get("due_at") or "",
            "repeat": item.get("repeat") or "",
            "sku": item.get("sku") or "",
        }
    return {"id": item.get("id"), "name": item.get("name"), "type": item.get("type") or ""}


def _error(message: str) -> Exception:
    from sonoscribe.scout.tools import ToolError as ScoutToolError

    return ScoutToolError(message)
