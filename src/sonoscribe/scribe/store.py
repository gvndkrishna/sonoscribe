"""Load and save vocanotes on the library."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sonoscribe.catalog import LibraryError, load_library, save_library
from sonoscribe.device import iso_now
from sonoscribe.scribe.model import number_vocanotes, public_vocanote, validate_vocanote
from sonoscribe.scribe.parse import local_now, next_repeat_due, normalize_repeat, parse_scribe, parse_stamp


def list_vocanotes(library: dict[str, Any] | None = None, *, secrets: bool = True) -> list[dict[str, Any]]:
    data = library if isinstance(library, dict) else load_library()
    gone = {
        str(item.get("id") or "").strip()
        for item in data.get("vocanote_gone") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    items: list[dict[str, Any]] = []
    for raw in data.get("vocanotes") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("id") in gone:
            continue
        if not secrets and raw.get("secret"):
            continue
        item = public_vocanote(raw)
        if item:
            items.append(item)
    return number_vocanotes(items)


def get_vocanote(note_id: str, library: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ident = str(note_id or "").strip()
    if not ident:
        return None
    for item in list_vocanotes(library):
        if item.get("id") == ident:
            return item
    return None


def create_from_text(text: str) -> dict[str, Any]:
    return upsert_vocanote({}, parse_text=text)


def upsert_vocanote(patch: dict[str, Any] | None, *, parse_text: str | None = None) -> dict[str, Any]:
    incoming = dict(patch) if isinstance(patch, dict) else {}
    spoken = str(parse_text or "").strip()
    if spoken:
        parsed = parse_scribe(spoken)
        incoming = {**parsed, **{key: value for key, value in incoming.items() if value not in (None, "")}}
        if not str(incoming.get("title") or "").strip():
            incoming["title"] = parsed["title"]
    library = load_library()
    items = [item for item in (library.get("vocanotes") or []) if isinstance(item, dict)]
    ident = str(incoming.get("id") or "").strip()
    gone = [
        item
        for item in (library.get("vocanote_gone") or [])
        if isinstance(item, dict) and item.get("id")
    ]
    gone_ids = {item.get("id") for item in gone}
    existing: dict[str, Any] | None = None
    index = -1
    if ident:
        for pos, item in enumerate(items):
            if item.get("id") == ident:
                existing = item
                index = pos
                break
        if existing is None and ident in gone_ids:
            raise LibraryError(["that vocanote was deleted."])
    merged = {**(existing or {}), **incoming}
    if existing:
        merged["id"] = existing["id"]
        merged["created_at"] = existing.get("created_at") or iso_now()
        if str(merged.get("due_at") or "") != str(existing.get("due_at") or ""):
            merged["notified_at"] = ""
    merged["updated_at"] = iso_now()
    cleaned, errors = validate_vocanote(merged)
    if cleaned is None:
        raise LibraryError(errors)
    if index >= 0:
        items[index] = cleaned
    else:
        items.append(cleaned)
    gone = [item for item in gone if item.get("id") != cleaned["id"]]
    save_library({**library, "vocanotes": items, "vocanote_gone": gone})
    numbered = get_vocanote(cleaned["id"])
    return numbered or public_vocanote(cleaned) or cleaned


def delete_vocanotes(ids: list[str] | str) -> dict[str, Any]:
    wanted = {str(item).strip() for item in (ids if isinstance(ids, list) else [ids]) if str(item).strip()}
    library = load_library()
    items = [item for item in (library.get("vocanotes") or []) if isinstance(item, dict)]
    kept = [item for item in items if item.get("id") not in wanted]
    stamp = iso_now()
    gone = [
        item
        for item in (library.get("vocanote_gone") or [])
        if isinstance(item, dict) and item.get("id") not in wanted
    ]
    gone.extend({"id": ident, "deleted_at": stamp} for ident in wanted)
    save_library({**library, "vocanotes": kept, "vocanote_gone": gone})
    return {"ok": True, "items": list_vocanotes()}


def dismiss_vocanote(note_id: str) -> dict[str, Any] | None:
    ident = str(note_id or "").strip()
    if not ident:
        return None
    for item in load_library().get("vocanotes") or []:
        if isinstance(item, dict) and item.get("id") == ident:
            if normalize_repeat(item.get("repeat")):
                return advance_repeat(ident)
            return mark_notified(ident)
    return None


def advance_repeat(note_id: str, when: datetime | None = None) -> dict[str, Any] | None:
    ident = str(note_id or "").strip()
    if not ident:
        return None
    library = load_library()
    stamp = when or local_now()
    items: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for item in library.get("vocanotes") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == ident:
            kind = normalize_repeat(item.get("repeat"))
            if not kind:
                return mark_notified(ident, when=stamp)
            due = parse_stamp(item.get("due_at")) or stamp
            nxt = next_repeat_due(kind, stamp, hour=due.hour, minute=due.minute, strict=True)
            item = {
                **item,
                "due_at": nxt.isoformat(timespec="seconds"),
                "notified_at": "",
                "updated_at": iso_now(),
            }
            found = item
        items.append(item)
    if found is None:
        return None
    save_library({**library, "vocanotes": items})
    return get_vocanote(ident)


def mark_notified(note_id: str, when: datetime | None = None) -> dict[str, Any] | None:
    ident = str(note_id or "").strip()
    if not ident:
        return None
    library = load_library()
    stamp = (when or local_now()).isoformat(timespec="seconds")
    items: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    for item in library.get("vocanotes") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == ident:
            item = {**item, "notified_at": stamp, "updated_at": iso_now()}
            found = item
        items.append(item)
    if found is None:
        return None
    save_library({**library, "vocanotes": items})
    return get_vocanote(ident)


def due_vocanotes(now: datetime | None = None) -> list[dict[str, Any]]:
    stamp = now or local_now()
    ready: list[dict[str, Any]] = []
    for item in load_library().get("vocanotes") or []:
        if not isinstance(item, dict) or not item.get("is_reminder") or item.get("notified_at"):
            continue
        due = parse_stamp(item.get("due_at"))
        if due is not None and due <= stamp:
            public = public_vocanote(item)
            if public:
                ready.append(public)
    return number_vocanotes(ready)
