"""Local dashboard preferences. Never stores the sync private key."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_ENV_SETTINGS = "SONOSCRIBE_SETTINGS"
THEMES = ("light", "dark")
ACCENTS = ("blue", "purple", "amber", "teal", "gray")
ACCENT_ALIASES = {
    "pink": "purple",
    "red": "amber",
    "orange": "amber",
    "green": "teal",
}
KEYCHAIN_SCOPES = ("local", "icloud")
SYNC_PROVIDERS = ("aws", "gcs", "azure")
SYNC_INTERVALS = (0, 300, 900, 1800, 3600)
DEFAULT_SYNC_INTERVAL = 900
TIMEZONE_OPTIONS: list[dict[str, str]] = [
    {"id": "local", "label": "This Mac"},
    {"id": "UTC", "label": "UTC"},
    {"id": "America/New_York", "label": "America/New York"},
    {"id": "America/Chicago", "label": "America/Chicago"},
    {"id": "America/Denver", "label": "America/Denver"},
    {"id": "America/Los_Angeles", "label": "America/Los Angeles"},
    {"id": "America/Sao_Paulo", "label": "America/São Paulo"},
    {"id": "Europe/London", "label": "Europe/London"},
    {"id": "Europe/Paris", "label": "Europe/Paris"},
    {"id": "Europe/Berlin", "label": "Europe/Berlin"},
    {"id": "Asia/Kolkata", "label": "Asia/Kolkata"},
    {"id": "Asia/Singapore", "label": "Asia/Singapore"},
    {"id": "Asia/Tokyo", "label": "Asia/Tokyo"},
    {"id": "Australia/Sydney", "label": "Australia/Sydney"},
]
TIMEZONES = tuple(item["id"] for item in TIMEZONE_OPTIONS)
CHART_IDS = (
    "mix",
    "versus",
    "types",
    "models",
    "model-wpm",
    "daily",
    "top",
    "routines",
    "routine-split",
    "hourly",
    "library",
)
CHART_GRID_COLS = 24
CHART_ROW_PX = 8
CHART_MIN_W = 3
CHART_MAX_W = 24
CHART_MIN_H = 20
CHART_MAX_H = 80
CHART_DEFAULT_W = 8
CHART_DEFAULT_H = 34
CHART_MIN_HEIGHT = 160
CHART_MAX_HEIGHT = 560
CHART_DEFAULT_HEIGHT = 220

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_path: Path | None = None
_cache_stamp: tuple[int, int] | None = None


def settings_path() -> Path:
    override = os.environ.get(_ENV_SETTINGS)
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Sonoscribe" / "settings.json"


def empty_settings() -> dict[str, Any]:
    return {
        "theme": "light",
        "accent": "amber",
        "timezone": "local",
        "reduce_motion": False,
        "private_mode": False,
        "lock": {"enabled": False, "method": "", "timeout_sec": 900},
        "keychain_scope": "local",
        "model": "large-v3-turbo",
        "custom_models": [],
        "username": "",
        "username_updated_at": None,
        "device": {"id": "", "serial": "", "name": "", "updated_at": "", "previous_ids": []},
        "devices": [],
        "sync": {
            "enabled": False,
            "provider": "",
            "bucket": "",
            "prefix": "",
            "account": "",
            "project": "",
            "last_sync_at": None,
            "last_error": None,
            "needs_confirm": False,
            "needs_key": False,
            "needs_create": False,
            "interval_sec": DEFAULT_SYNC_INTERVAL,
            "what": {"library": True, "stats": False},
        },
        "charts": default_charts(),
    }


def default_charts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    x = 0
    y = 0
    for chart_id in CHART_IDS:
        w = 16 if chart_id == "library" else CHART_DEFAULT_W
        if x + w > CHART_GRID_COLS:
            x = 0
            y += CHART_DEFAULT_H
        out.append({"id": chart_id, "x": x, "y": y, "w": w, "h": CHART_DEFAULT_H})
        x += w
        if x >= CHART_GRID_COLS:
            x = 0
            y += CHART_DEFAULT_H
    return out


def _chart_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _charts_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a["x"] < b["x"] + b["w"]
        and a["x"] + a["w"] > b["x"]
        and a["y"] < b["y"] + b["h"]
        and a["y"] + a["h"] > b["y"]
    )


def _place_chart(existing: list[dict[str, Any]], w: int, h: int) -> tuple[int, int]:
    max_y = max((item["y"] + item["h"] for item in existing), default=0)
    for y in range(0, max_y + 1):
        for x in range(0, CHART_GRID_COLS - w + 1):
            cand = {"x": x, "y": y, "w": w, "h": h}
            if not any(_charts_overlap(cand, item) for item in existing):
                return x, y
    return 0, max_y


def _chart_size(item: dict[str, Any]) -> tuple[int, int]:
    if item.get("w") is not None:
        w = _chart_int(item.get("w"), CHART_DEFAULT_W)
    else:
        cols = min(3, max(1, _chart_int(item.get("cols"), 1)))
        w = {1: 8, 2: 16, 3: 24}[cols]
    if item.get("h") is not None:
        h = _chart_int(item.get("h"), CHART_DEFAULT_H)
    elif item.get("height") is not None:
        px = min(
            CHART_MAX_HEIGHT,
            max(CHART_MIN_HEIGHT, _chart_int(item.get("height"), CHART_DEFAULT_HEIGHT)),
        )
        h = round(px / CHART_ROW_PX)
    else:
        h = CHART_DEFAULT_H
    w = min(CHART_MAX_W, max(CHART_MIN_W, w))
    h = min(CHART_MAX_H, max(CHART_MIN_H, h))
    return w, h


def _clean_charts(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return default_charts()
    if not isinstance(raw, list):
        return default_charts()
    seen: set[str] = set()
    positioned: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        chart_id = str(item.get("id") or "").strip()
        if chart_id not in CHART_IDS or chart_id in seen:
            continue
        seen.add(chart_id)
        w, h = _chart_size(item)
        has_pos = "x" in item and "y" in item
        if has_pos:
            x = min(CHART_GRID_COLS - w, max(0, _chart_int(item.get("x"), 0)))
            y = max(0, _chart_int(item.get("y"), 0))
            positioned.append({"id": chart_id, "x": x, "y": y, "w": w, "h": h})
        else:
            pending.append({"id": chart_id, "w": w, "h": h})
    out = list(positioned)
    for item in pending:
        x, y = _place_chart(out, item["w"], item["h"])
        out.append({"id": item["id"], "x": x, "y": y, "w": item["w"], "h": item["h"]})
    return out


def clear_settings_cache() -> None:
    global _cache, _cache_path, _cache_stamp
    with _lock:
        _cache = None
        _cache_path = None
        _cache_stamp = None


def validate_settings(raw: Any) -> dict[str, Any]:
    from sonoscribe.device import ensure_device
    from sonoscribe.profile import clean_username

    data = empty_settings()
    if not isinstance(raw, dict):
        ensure_device(data)
        _upsert_this_device(data)
        return data
    theme = str(raw.get("theme") or "").strip()
    if theme in THEMES:
        data["theme"] = theme
    data["accent"] = _clean_accent(raw.get("accent"))
    timezone = str(raw.get("timezone") or "").strip()
    if timezone in TIMEZONES:
        data["timezone"] = timezone
    data["reduce_motion"] = bool(raw.get("reduce_motion"))
    data["private_mode"] = bool(raw.get("private_mode"))
    from sonoscribe.lock import clean_lock

    data["lock"] = clean_lock(raw.get("lock"))
    scope = str(raw.get("keychain_scope") or "").strip()
    if scope in KEYCHAIN_SCOPES:
        data["keychain_scope"] = scope
    from sonoscribe.transcriber import clean_model

    data["custom_models"] = _clean_custom_models(raw.get("custom_models"))
    custom_ids = [item["id"] for item in data["custom_models"]]
    data["model"] = clean_model(raw.get("model"), custom_ids=custom_ids)
    data["username"] = clean_username(raw.get("username"))
    stamp = raw.get("username_updated_at")
    data["username_updated_at"] = str(stamp) if stamp else None
    if isinstance(raw.get("device"), dict):
        data["device"] = dict(raw["device"])
    previous_id = str(data["device"].get("id") or "").strip()
    ensure_device(data)
    data["devices"] = _clean_devices(raw.get("devices"))
    if previous_id and previous_id != data["device"]["id"]:
        data["devices"] = [item for item in data["devices"] if item.get("id") != previous_id]
    _upsert_this_device(data)
    sync_raw = raw.get("sync")
    if isinstance(sync_raw, dict):
        data["sync"] = _clean_sync(sync_raw)
    data["charts"] = _clean_charts(raw.get("charts"))
    return data


def public_settings(data: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = validate_settings(data if data is not None else load_settings())
    return {
        "theme": cleaned["theme"],
        "accent": cleaned["accent"],
        "timezone": cleaned["timezone"],
        "reduce_motion": bool(cleaned["reduce_motion"]),
        "private_mode": bool(cleaned["private_mode"]),
        "lock": dict(cleaned["lock"]),
        "keychain_scope": cleaned["keychain_scope"],
        "model": cleaned["model"],
        "custom_models": list(cleaned["custom_models"]),
        "username": cleaned["username"],
        "device": dict(cleaned["device"]),
        "devices": list(cleaned["devices"]),
        "sync": dict(cleaned["sync"]),
        "sync_intervals": list(SYNC_INTERVALS),
        "timezones": list(TIMEZONE_OPTIONS),
        "accents": list(ACCENTS),
        "themes": list(THEMES),
        "models": _public_model_choices(cleaned["custom_models"]),
        "charts": list(cleaned["charts"]),
    }


def public_account(data: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = validate_settings(data if data is not None else load_settings())
    this_id = str(cleaned["device"]["id"])
    return {
        "username": cleaned["username"],
        "private_mode": bool(cleaned["private_mode"]),
        "lock": dict(cleaned["lock"]),
        "device": dict(cleaned["device"]),
        "devices": [
            {**item, "this": item.get("id") == this_id} for item in cleaned["devices"]
        ],
    }


def resolve_model(cli: str | None = None) -> str:
    from sonoscribe.transcriber import DEFAULT_MODEL, clean_model

    settings = load_settings()
    custom_ids = [item["id"] for item in settings.get("custom_models") or []]
    if cli:
        return clean_model(cli, custom_ids=custom_ids)
    return clean_model(settings.get("model"), DEFAULT_MODEL, custom_ids=custom_ids)


def lookup_model(key: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    from sonoscribe.transcriber import MODEL_LABELS, MODELS

    cleaned = validate_settings(data if data is not None else load_settings())
    wanted = str(key or "").strip()
    if wanted in MODELS:
        return {"id": wanted, "label": MODEL_LABELS[wanted], "path": None, "custom": False}
    for item in cleaned.get("custom_models") or []:
        if item.get("id") == wanted:
            return {
                "id": item["id"],
                "label": item["name"],
                "path": item["path"],
                "custom": True,
            }
    return None


def add_custom_model(path: str, name: str = "") -> dict[str, Any]:
    from sonoscribe.transcriber import custom_model_id, local_model_error, normalize_model_dir

    error = local_model_error(path)
    if error:
        raise ValueError(error)
    folder = str(normalize_model_dir(path))
    label = str(name or "").strip()[:80] or Path(folder).name[:80]
    record = {"id": custom_model_id(folder), "name": label, "path": folder}
    current = load_settings()
    models = [item for item in current.get("custom_models") or [] if item.get("id") != record["id"]]
    if len(models) >= 12:
        raise ValueError("12 custom models max.")
    models.append(record)
    current["custom_models"] = models
    current["model"] = record["id"]
    return save_settings(current)


def remove_custom_model(model_id: str) -> dict[str, Any]:
    from sonoscribe.transcriber import DEFAULT_MODEL

    wanted = str(model_id or "").strip()
    current = load_settings()
    current["custom_models"] = [
        item for item in current.get("custom_models") or [] if item.get("id") != wanted
    ]
    if current.get("model") == wanted:
        current["model"] = DEFAULT_MODEL
    return save_settings(current)


def public_model_state(live: dict[str, Any] | None = None) -> dict[str, Any]:
    from sonoscribe.transcriber import clean_model, public_models

    cleaned = validate_settings(load_settings())
    live = live if isinstance(live, dict) else {}
    status = str(live.get("status") or "ready")
    if status not in {"ready", "loading", "error"}:
        status = "ready"
    custom_ids = [item["id"] for item in cleaned.get("custom_models") or []]
    return {
        "model": clean_model(live.get("model") or cleaned["model"], custom_ids=custom_ids),
        "active": clean_model(live.get("active") or cleaned["model"], custom_ids=custom_ids),
        "status": status,
        "error": str(live.get("error") or ""),
        "models": public_models(cleaned.get("custom_models")),
    }


def _clean_accent(raw: Any) -> str:
    accent = str(raw or "").strip()
    if accent in ACCENTS:
        return accent
    return ACCENT_ALIASES.get(accent, "amber")


def _public_model_choices(custom_models: Any = None) -> list[dict[str, Any]]:
    from sonoscribe.transcriber import public_models

    return public_models(custom_models)


def _clean_custom_models(raw: Any) -> list[dict[str, str]]:
    from sonoscribe.transcriber import custom_model_id, local_model_error, normalize_model_dir

    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path or local_model_error(path):
            continue
        try:
            folder = str(normalize_model_dir(path))
        except OSError:
            continue
        key = str(item.get("id") or "").strip() or custom_model_id(folder)
        if key in seen:
            continue
        seen.add(key)
        name = str(item.get("name") or Path(folder).name).strip()[:80] or Path(folder).name[:80]
        out.append({"id": key, "name": name, "path": folder})
        if len(out) >= 12:
            break
    return out


def sync_what(data: dict[str, Any] | None = None) -> dict[str, bool]:
    cleaned = validate_settings(data if data is not None else load_settings())
    what = cleaned["sync"].get("what") or {}
    return {
        "profile": True,
        "library": bool(what.get("library", True)),
        "stats": bool(what.get("stats")) and not bool(cleaned.get("private_mode")),
    }


def load_settings(path: Path | None = None) -> dict[str, Any]:
    target = (path or settings_path()).resolve()
    with _lock:
        return _load_locked(target)


def save_settings(settings: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    cleaned = validate_settings(settings)
    target = (path or settings_path()).resolve()
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
        _remember(target, cleaned)
        return cleaned


def update_settings(patch: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    from sonoscribe.device import ensure_device, iso_now
    from sonoscribe.profile import clean_username

    current = load_settings(path)
    if "theme" in patch:
        current["theme"] = patch["theme"]
    if "accent" in patch:
        current["accent"] = patch["accent"]
    if "timezone" in patch:
        current["timezone"] = patch["timezone"]
    if "reduce_motion" in patch:
        current["reduce_motion"] = bool(patch["reduce_motion"])
    if "private_mode" in patch:
        current["private_mode"] = bool(patch["private_mode"])
    if isinstance(patch.get("lock"), dict):
        merged = dict(current.get("lock") or empty_settings()["lock"])
        incoming = patch["lock"]
        for key in ("enabled", "method", "timeout_sec"):
            if key in incoming:
                merged[key] = incoming[key]
        current["lock"] = merged
    if "keychain_scope" in patch:
        current["keychain_scope"] = patch["keychain_scope"]
    if "model" in patch:
        current["model"] = patch["model"]
    if "custom_models" in patch:
        current["custom_models"] = patch["custom_models"]
    if "charts" in patch and isinstance(patch["charts"], list):
        current["charts"] = patch["charts"]
    if "username" in patch:
        name = clean_username(patch["username"])
        if name != current.get("username"):
            current["username"] = name
            current["username_updated_at"] = iso_now() if name else None
        if "username_updated_at" in patch:
            stamp = patch.get("username_updated_at")
            current["username_updated_at"] = str(stamp) if stamp else None
    if isinstance(patch.get("device"), dict):
        ensure_device(current)
        name = str(patch["device"].get("name") or "").strip()[:80]
        if name and name != current["device"].get("name"):
            current["device"]["name"] = name
            current["device"]["updated_at"] = iso_now()
        _upsert_this_device(current)
    if "devices" in patch:
        current["devices"] = _clean_devices(patch.get("devices"))
        _upsert_this_device(current)
    if isinstance(patch.get("sync"), dict):
        incoming = dict(patch["sync"])
        what_patch = incoming.pop("what", None)
        merged = dict(current["sync"])
        merged.update(incoming)
        if isinstance(what_patch, dict):
            what = dict(merged.get("what") or empty_settings()["sync"]["what"])
            if "library" in what_patch:
                what["library"] = bool(what_patch["library"])
            if "stats" in what_patch:
                what["stats"] = bool(what_patch["stats"])
            merged["what"] = what
        current["sync"] = merged
    return save_settings(current, path)


def _clean_sync(raw: dict[str, Any]) -> dict[str, Any]:
    sync = empty_settings()["sync"]
    sync["enabled"] = bool(raw.get("enabled"))
    provider = str(raw.get("provider") or "").strip()
    if provider in SYNC_PROVIDERS:
        sync["provider"] = provider
    sync["bucket"] = str(raw.get("bucket") or "").strip()
    sync["prefix"] = str(raw.get("prefix") or "").strip().strip("/")
    sync["account"] = str(raw.get("account") or "").strip()
    sync["project"] = str(raw.get("project") or "").strip()
    last_sync = raw.get("last_sync_at")
    sync["last_sync_at"] = str(last_sync) if last_sync else None
    error = raw.get("last_error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        details = str(error.get("details") or "").strip()
        kind = str(error.get("kind") or "").strip()
        if message:
            payload = {"message": message, "details": details}
            if kind:
                payload["kind"] = kind
            sync["last_error"] = payload
        else:
            sync["last_error"] = None
    elif error:
        sync["last_error"] = {"message": str(error), "details": ""}
    sync["needs_confirm"] = bool(raw.get("needs_confirm"))
    sync["needs_key"] = bool(raw.get("needs_key"))
    sync["needs_create"] = bool(raw.get("needs_create"))
    try:
        interval = int(raw.get("interval_sec"))
    except (TypeError, ValueError):
        interval = DEFAULT_SYNC_INTERVAL
    sync["interval_sec"] = interval if interval in SYNC_INTERVALS else DEFAULT_SYNC_INTERVAL
    what_raw = raw.get("what")
    what = dict(sync["what"])
    if isinstance(what_raw, dict):
        if "library" in what_raw:
            what["library"] = bool(what_raw["library"])
        if "stats" in what_raw:
            what["stats"] = bool(what_raw["stats"])
    sync["what"] = what
    return sync


def _clean_devices(raw: Any) -> list[dict[str, str]]:
    from sonoscribe.device import clean_device_ids

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
        previous_ids = clean_device_ids(item.get("previous_ids")) if "previous_ids" in item else []
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


def _upsert_this_device(data: dict[str, Any]) -> None:
    from sonoscribe.device import ensure_device, is_alias_of

    ensure_device(data)
    this = {
        "id": str(data["device"]["id"]),
        "serial": str(data["device"].get("serial") or data["device"]["id"]),
        "name": str(data["device"]["name"]),
        "updated_at": str(data["device"].get("updated_at") or ""),
        "previous_ids": list(data["device"].get("previous_ids") or []),
    }
    if not this["previous_ids"]:
        this.pop("previous_ids")
    roster = [
        item
        for item in (data.get("devices") or [])
        if item.get("id") != this["id"] and not is_alias_of(item, data["device"])
    ]
    roster.insert(0, this)
    data["devices"] = roster
    data["device"] = dict(this)
    if "previous_ids" not in data["device"]:
        data["device"]["previous_ids"] = []


def _file_stamp(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _remember(target: Path, data: dict[str, Any]) -> None:
    global _cache, _cache_path, _cache_stamp
    _cache = data
    _cache_path = target
    _cache_stamp = _file_stamp(target)


def _load_locked(target: Path) -> dict[str, Any]:
    global _cache, _cache_path, _cache_stamp
    stamp = _file_stamp(target)
    if (
        _cache is not None
        and _cache_path == target
        and stamp is not None
        and stamp == _cache_stamp
    ):
        return _cache
    raw: Any = None
    persist = False
    if target.exists():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
            persist = True
        if not isinstance(raw, dict) or not str((raw.get("device") or {}).get("id") or "").strip():
            persist = True
    else:
        raw = {}
        persist = True
    previous = {}
    if isinstance(raw, dict) and isinstance(raw.get("device"), dict):
        previous = dict(raw["device"])
    data = validate_settings(raw)
    this = data["device"]
    old_id = str(previous.get("id") or "").strip()
    raw_devices = raw.get("devices") if isinstance(raw, dict) else []
    raw_ids = {
        str(item.get("id") or "").strip()
        for item in (raw_devices or [])
        if isinstance(item, dict)
    }
    new_ids = {str(item.get("id") or "").strip() for item in data.get("devices") or []}
    if old_id != this["id"] or str(previous.get("serial") or "") != this["serial"] or (raw_ids - new_ids):
        persist = True
        if old_id and old_id != this["id"]:
            from sonoscribe.catalog import remap_device_id

            remap_device_id(old_id, str(this["id"]))
    if persist:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        stamp = _file_stamp(target)
    _remember(target, data)
    return data
