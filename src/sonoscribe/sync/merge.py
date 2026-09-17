"""Merge a decrypted cloud snapshot with this Mac’s local copy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sonoscribe.catalog import validate_library
from sonoscribe.device import is_alias_of, is_this_device_only
from sonoscribe.stats import clean_stats_blob, merge_stats_blobs

PAYLOAD_VERSION = 2


def empty_payload() -> dict[str, Any]:
    return {
        "v": PAYLOAD_VERSION,
        "username": "",
        "username_updated_at": None,
        "devices": [],
        "commands": [],
        "routines": [],
        "variables": [],
        "stats": {},
    }


def parse_plain(raw: Any) -> dict[str, Any]:
    data = empty_payload()
    if not isinstance(raw, dict):
        return data
    if _looks_like_library(raw) and raw.get("v") != PAYLOAD_VERSION:
        library = validate_library(raw)
        data["commands"] = library["commands"]
        data["routines"] = library["routines"]
        data["variables"] = library.get("variables") or []
        return data
    data["username"] = str(raw.get("username") or "").strip()[:40]
    stamp = raw.get("username_updated_at")
    data["username_updated_at"] = str(stamp) if stamp else None
    data["devices"] = _clean_devices(raw.get("devices"))
    try:
        library = validate_library({"commands": raw.get("commands") or [], "routines": raw.get("routines") or [], "variables": raw.get("variables") or []})
        data["commands"] = library["commands"]
        data["routines"] = library["routines"]
        data["variables"] = library.get("variables") or []
    except Exception:
        data["commands"] = []
        data["routines"] = []
        data["variables"] = []
    stats_raw = raw.get("stats")
    if isinstance(stats_raw, dict):
        cleaned: dict[str, Any] = {}
        for key, value in stats_raw.items():
            device_id = str(key or "").strip()
            if not device_id or not isinstance(value, dict):
                continue
            cleaned[device_id] = clean_stats_blob(value)
        data["stats"] = cleaned
    return data


def _is_local_only(item: dict[str, Any], this_id: str) -> bool:
    return is_this_device_only(item, this_id) or bool(item.get("secret"))


def _without_secrets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if not item.get("secret")]


def outgoing_library(items: list[dict[str, Any]], this_id: str) -> list[dict[str, Any]]:
    return [item for item in items if not _is_local_only(item, this_id)]


def merge_payloads(
    *,
    local: dict[str, Any],
    remote: dict[str, Any],
    this_id: str,
    what: dict[str, bool],
) -> dict[str, Any]:
    local = parse_plain(local)
    remote = parse_plain(remote)
    remote["commands"] = _without_secrets(remote.get("commands") or [])
    remote["routines"] = _without_secrets(remote.get("routines") or [])
    remote["variables"] = _without_secrets(remote.get("variables") or [])
    merged = empty_payload()
    if what.get("profile", True):
        merged["username"], merged["username_updated_at"] = _newer_username(local, remote)
        merged["devices"] = _merge_devices(local["devices"], remote["devices"], this_id, local)
    else:
        merged["username"] = remote["username"]
        merged["username_updated_at"] = remote["username_updated_at"]
        merged["devices"] = list(remote["devices"])
    if what.get("library", True):
        aliases = _alias_ids(local, remote, this_id)
        merged["commands"] = _remap_item_devices(
            _merge_items(local["commands"], remote["commands"], this_id),
            aliases,
            this_id,
        )
        merged["routines"] = _remap_item_devices(
            _merge_items(local["routines"], remote["routines"], this_id),
            aliases,
            this_id,
        )
        merged["variables"] = _merge_items(local.get("variables") or [], remote.get("variables") or [], this_id)
    else:
        merged["commands"] = list(remote["commands"])
        merged["routines"] = list(remote["routines"])
        merged["variables"] = list(remote.get("variables") or [])
    if what.get("stats"):
        merged["stats"] = _merge_stats(local, remote, this_id)
    else:
        merged["stats"] = dict(remote["stats"])
    return merged


def apply_payload(
    *,
    local_library: dict[str, Any],
    remote: dict[str, Any],
    this_id: str,
    what: dict[str, bool],
) -> dict[str, Any]:
    remote = parse_plain(remote)
    remote["commands"] = _without_secrets(remote.get("commands") or [])
    remote["routines"] = _without_secrets(remote.get("routines") or [])
    remote["variables"] = _without_secrets(remote.get("variables") or [])
    result = {
        "username": None,
        "username_updated_at": None,
        "devices": None,
        "library": None,
        "stats": None,
    }
    if what.get("profile", True):
        result["username"] = remote["username"]
        result["username_updated_at"] = remote["username_updated_at"]
        result["devices"] = list(remote["devices"])
    if what.get("library", True):
        local_commands = [item for item in local_library.get("commands") or [] if _is_local_only(item, this_id)]
        local_routines = [item for item in local_library.get("routines") or [] if _is_local_only(item, this_id)]
        local_variables = [item for item in local_library.get("variables") or [] if _is_local_only(item, this_id)]
        result["library"] = {
            "commands": _force_items(local_commands, list(remote["commands"])),
            "routines": _force_items(local_routines, list(remote["routines"])),
            "variables": _force_items(local_variables, list(remote.get("variables") or [])),
        }
    if what.get("stats"):
        result["stats"] = dict(remote["stats"])
    return result


def _looks_like_library(raw: dict[str, Any]) -> bool:
    return "commands" in raw and "username" not in raw and "devices" not in raw and "stats" not in raw


def _clean_devices(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        device_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()[:80]
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        serial = str(item.get("serial") or device_id).strip()
        previous_ids = []
        raw_previous = item.get("previous_ids")
        if isinstance(raw_previous, list):
            previous_ids = [str(value).strip() for value in raw_previous if str(value).strip()]
        record = {
            "id": device_id,
            "serial": serial or device_id,
            "name": name or "Mac",
            "updated_at": str(item.get("updated_at") or ""),
        }
        if previous_ids:
            record["previous_ids"] = previous_ids
        out.append(record)
    return out


def _newer_username(local: dict[str, Any], remote: dict[str, Any]) -> tuple[str, str | None]:
    if _is_newer(local.get("username_updated_at"), remote.get("username_updated_at")):
        return local["username"], local["username_updated_at"]
    if remote["username"]:
        return remote["username"], remote["username_updated_at"]
    return local["username"], local["username_updated_at"]


def _merge_devices(
    local: list[dict[str, str]],
    remote: list[dict[str, str]],
    this_id: str,
    local_payload: dict[str, Any],
) -> list[dict[str, str]]:
    by_id = {item["id"]: dict(item) for item in remote}
    for item in local:
        existing = by_id.get(item["id"])
        if existing is None or _is_newer(item.get("updated_at"), existing.get("updated_at")):
            by_id[item["id"]] = dict(item)
    mine = this_device_record(local_payload, this_id)
    if mine:
        by_id[this_id] = mine
    kept: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in by_id.values():
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen:
            continue
        if item_id != this_id and is_alias_of(item, mine or {"id": this_id}):
            continue
        seen.add(item_id)
        kept.append(item)
    return kept


def this_device_record(local_payload: dict[str, Any], this_id: str) -> dict[str, str] | None:
    for item in local_payload.get("devices") or []:
        if item.get("id") == this_id:
            return dict(item)
    return None


def _alias_ids(local: dict[str, Any], remote: dict[str, Any], this_id: str) -> set[str]:
    this = this_device_record(local, this_id) or {"id": this_id}
    aliases = {str(value) for value in (this.get("previous_ids") or []) if value}
    for item in list(local.get("devices") or []) + list(remote.get("devices") or []):
        item_id = str(item.get("id") or "")
        if item_id and is_alias_of(item, this):
            aliases.add(item_id)
    return aliases


def _remap_item_devices(items: list[dict[str, Any]], aliases: set[str], this_id: str) -> list[dict[str, Any]]:
    aliases = {value for value in aliases if value and value != this_id}
    if not aliases:
        return items
    out: list[dict[str, Any]] = []
    for item in items:
        assigned = item.get("devices")
        if not isinstance(assigned, list) or not assigned:
            out.append(item)
            continue
        seen: set[str] = set()
        rewritten: list[str] = []
        for value in assigned:
            next_id = this_id if value in aliases else str(value)
            if not next_id or next_id in seen:
                continue
            seen.add(next_id)
            rewritten.append(next_id)
        if rewritten != assigned:
            item = {**item, "devices": rewritten}
        out.append(item)
    return out


def _merge_stats(local: dict[str, Any], remote: dict[str, Any], this_id: str) -> dict[str, Any]:
    this = this_device_record(local, this_id) or {"id": this_id}
    roster = list(local.get("devices") or []) + list(remote.get("devices") or [])
    local_stats = local.get("stats") or {}
    remote_stats = remote.get("stats") or {}
    previous = {str(value) for value in (this.get("previous_ids") or [])}
    merged: dict[str, Any] = {}
    mine = merge_stats_blobs(local_stats.get(this_id) or {}, remote_stats.get(this_id) or {})
    keys = set(local_stats) | set(remote_stats)
    for device_id in keys:
        blob = merge_stats_blobs(local_stats.get(device_id) or {}, remote_stats.get(device_id) or {})
        lookup = {"id": device_id, "serial": device_id, "name": ""}
        for item in roster:
            if item.get("id") == device_id:
                lookup = item
                break
        if device_id == this_id or device_id in previous or is_alias_of(lookup, this):
            mine = merge_stats_blobs(mine, blob)
            continue
        merged[device_id] = blob
    merged[this_id] = mine
    return merged


def _merge_items(local: list[dict[str, Any]], remote: list[dict[str, Any]], this_id: str) -> list[dict[str, Any]]:
    keep_local = [item for item in local if _is_local_only(item, this_id)]
    remote_keep = [item for item in remote if not _is_local_only(item, this_id)]
    local_shared = outgoing_library(local, this_id)
    return _force_items(keep_local, _prefer_newer_by_id(remote_keep, local_shared))


def _force_items(overlay: list[dict[str, Any]], base: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in base + overlay:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        if item_id not in by_id:
            order.append(item_id)
        by_id[item_id] = item
    return [by_id[item_id] for item_id in order]


def _prefer_newer_by_id(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in secondary + primary:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        existing = by_id.get(item_id)
        if existing is None:
            by_id[item_id] = item
            order.append(item_id)
            continue
        if _is_newer(item.get("updated_at"), existing.get("updated_at")):
            by_id[item_id] = item
    return [by_id[item_id] for item_id in order]


def _is_newer(candidate: Any, other: Any) -> bool:
    left = _parse_time(candidate)
    right = _parse_time(other)
    if left is None:
        return False
    if right is None:
        return True
    return left > right


def _parse_time(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
