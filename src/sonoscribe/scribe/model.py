"""Vocanote shape. No library I/O here."""

from __future__ import annotations

import uuid
from typing import Any

from sonoscribe.device import clean_device_ids, iso_now
from sonoscribe.scribe.parse import (
    coerce_due,
    local_now,
    next_repeat_due,
    normalize_repeat,
    parse_scribe,
    parse_stamp,
)

TITLE_MAX = 200
BODY_MAX = 8000


def validate_vocanote(raw: Any, prefix: str = "Vocanote") -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(raw, dict):
        return None, [f"{prefix} must be an object"]
    errors: list[str] = []
    title = str(raw.get("title") or "").strip()[:TITLE_MAX]
    if not title:
        errors.append(f"{prefix}: title is required")
    note_id = str(raw.get("id") or "").strip() or f"voc-{uuid.uuid4().hex[:10]}"
    body = str(raw.get("body") or "")[:BODY_MAX]
    is_todo = bool(raw.get("is_todo"))
    if "is_reminder" in raw:
        is_reminder = bool(raw.get("is_reminder"))
    else:
        is_reminder = bool(raw.get("due_at") or raw.get("repeat"))
    repeat = normalize_repeat(raw.get("repeat"))
    if repeat:
        is_reminder = True
    due_at = coerce_due(raw.get("due_at")) if is_reminder else ""
    notified = parse_stamp(raw.get("notified_at"))
    notified_at = notified.isoformat(timespec="seconds") if notified else ""
    if is_reminder and not due_at:
        parsed = parse_scribe(title)
        due_at = str(parsed.get("due_at") or "")
        if not repeat:
            repeat = normalize_repeat(parsed.get("repeat"))
    if is_reminder and not due_at and repeat:
        due_at = next_repeat_due(repeat, local_now()).isoformat(timespec="seconds")
    if is_reminder and not due_at:
        errors.append(f"{prefix}: reminder needs a time")
    if not is_reminder:
        due_at = ""
        notified_at = ""
        repeat = ""
    if due_at:
        is_reminder = True
    created_at = str(raw.get("created_at") or "") or iso_now()
    updated_at = str(raw.get("updated_at") or "") or iso_now()
    if errors:
        return None, errors
    item: dict[str, Any] = {
        "id": note_id,
        "title": title,
        "body": body,
        "is_note": True,
        "is_todo": is_todo,
        "is_reminder": is_reminder,
        "due_at": due_at,
        "repeat": repeat,
        "notified_at": notified_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "devices": clean_device_ids(raw.get("devices")),
    }
    if bool(raw.get("secret")):
        item["secret"] = True
    return item, []


def public_vocanote(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    data = {
        "id": item.get("id"),
        "title": item.get("title") or "",
        "body": item.get("body") or "",
        "is_note": True,
        "is_todo": bool(item.get("is_todo")),
        "is_reminder": bool(item.get("is_reminder")),
        "due_at": item.get("due_at") or "",
        "repeat": normalize_repeat(item.get("repeat")),
        "notified_at": item.get("notified_at") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or item.get("created_at") or "",
        "devices": list(item.get("devices") or []),
    }
    if item.get("secret"):
        data["secret"] = True
    if item.get("sku"):
        data["sku"] = item.get("sku")
    if item.get("n"):
        data["n"] = item.get("n")
    return data


def number_vocanotes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        items,
        key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for index, item in enumerate(ordered):
        note = dict(item)
        note["n"] = index + 1
        note["sku"] = f"vn–{index + 1:02d}"
        out.append(note)
    return out
