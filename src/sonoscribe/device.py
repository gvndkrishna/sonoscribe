"""This Mac’s identity in the synced device roster."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any

_SERIAL_RE = re.compile(r"^[A-Za-z0-9-]{8,40}$")
_GENERATED_RE = re.compile(r"^dev-[0-9a-f]{12}$")
_serial_cache: str | None = None


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_device_name() -> str:
    named = _computer_name()
    if named:
        return named
    return (platform.node() or "This Mac").strip() or "This Mac"


def new_device_id() -> str:
    return f"dev-{uuid.uuid4().hex[:12]}"


def clear_serial_cache() -> None:
    global _serial_cache
    _serial_cache = None


def hardware_serial() -> str:
    global _serial_cache
    if _serial_cache is not None:
        return _serial_cache
    found = _ioreg_serial()
    if found:
        _serial_cache = found
        return found
    _serial_cache = ""
    return ""


def clean_device_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if not value or value in seen or len(value) > 80:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= 24:
            break
    return out


def item_on_device(item: dict[str, Any], device_id: str) -> bool:
    assigned = clean_device_ids(item.get("devices"))
    return not assigned or device_id in assigned


def is_this_device_only(item: dict[str, Any], device_id: str) -> bool:
    assigned = set(clean_device_ids(item.get("devices")))
    return assigned == {device_id}


def is_generated_id(device_id: str) -> bool:
    return bool(_GENERATED_RE.fullmatch(str(device_id or "").strip()))


def is_alias_of(item: dict[str, Any], this: dict[str, Any]) -> bool:
    item_id = str(item.get("id") or "").strip()
    this_id = str(this.get("id") or "").strip()
    if not item_id or not this_id or item_id == this_id:
        return False
    previous = set(clean_device_ids(this.get("previous_ids")))
    if item_id in previous:
        return True
    this_serial = str(this.get("serial") or this_id).strip()
    item_serial = str(item.get("serial") or item_id).strip()
    if this_serial and item_serial == this_serial:
        return True
    this_name = str(this.get("name") or "").strip()
    item_name = str(item.get("name") or "").strip()
    if is_generated_id(item_id) and not is_generated_id(this_id) and this_name and item_name == this_name:
        return True
    return False


def ensure_device(settings: dict[str, Any]) -> bool:
    raw = settings.get("device") if isinstance(settings.get("device"), dict) else {}
    device_id = str(raw.get("id") or "").strip()
    serial = str(raw.get("serial") or "").strip()
    name = str(raw.get("name") or "").strip()[:80]
    previous_ids = clean_device_ids(raw.get("previous_ids"))
    changed = False
    hardware = hardware_serial()
    if hardware:
        if serial != hardware:
            serial = hardware
            changed = True
        if device_id != hardware:
            if device_id and device_id not in previous_ids:
                previous_ids.append(device_id)
            device_id = hardware
            changed = True
    if not device_id:
        device_id = serial or new_device_id()
        changed = True
    if not serial:
        serial = device_id
        changed = True
    if not name:
        name = default_device_name()[:80]
        changed = True
    settings["device"] = {
        "id": device_id,
        "serial": serial,
        "name": name,
        "updated_at": str(raw.get("updated_at") or ""),
        "previous_ids": previous_ids,
    }
    return changed


def this_device(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings is None:
        from sonoscribe.settings import load_settings

        settings = load_settings()
    ensure_device(settings)
    device = settings["device"]
    return {
        "id": str(device["id"]),
        "serial": str(device.get("serial") or device["id"]),
        "name": str(device["name"]),
        "updated_at": str(device.get("updated_at") or ""),
        "previous_ids": list(device.get("previous_ids") or []),
    }


def this_device_id(settings: dict[str, Any] | None = None) -> str:
    return this_device(settings)["id"]


def _ioreg_serial() -> str:
    binary = shutil.which("ioreg")
    if not binary:
        return ""
    try:
        result = subprocess.run(
            [binary, "-d2", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        if "IOPlatformSerialNumber" not in line:
            continue
        _, _, rest = line.partition("=")
        value = rest.strip().strip('"').strip()
        if _SERIAL_RE.fullmatch(value):
            return value
    return ""


def _computer_name() -> str:
    binary = shutil.which("scutil")
    if not binary:
        return ""
    try:
        result = subprocess.run(
            [binary, "--get", "ComputerName"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()
