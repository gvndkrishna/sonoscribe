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
SCOUT_PROVIDERS = ("openai", "anthropic", "grok", "kimi", "bedrock", "local")
SCOUT_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-0",
    "grok": "grok-3",
    "kimi": "moonshot-v1-auto",
    "bedrock": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "local": "llama3.2",
}
SCOUT_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
SCOUT_DEFAULT_BEDROCK_REGION = "us-east-1"
SCOUT_TOOLS = ("search", "weather", "fetch", "open_page", "run_script", "write_file", "read_file")
SCOUT_TOOL_CATALOG = SCOUT_TOOLS + ("capture_screen",)
SCOUT_AUTO_DEFAULT = ("search", "weather", "fetch", "open_page")
SCOUT_TOOLS_VERSION = 2
_LEGACY_SCOUT_TOOLS = ("search", "fetch", "run_script", "write_file", "read_file")
_PRE_WEATHER_TOOLS = frozenset({"search", "fetch", "open_page", "run_script", "write_file", "read_file"})
_PRE_WEATHER_AUTO = frozenset({"search", "fetch", "open_page"})
SCOUT_TOKEN_LIMITS = (0, 2000, 4000, 8000, 16000, 32000)
SCOUT_DURATION_LIMITS = (0, 30, 60, 90, 180, 300)
SCOUT_DEFAULT_TOKENS = 8000
SCOUT_DEFAULT_DURATION = 90
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
DEFAULT_CHART_IDS = (
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
EXTRA_CHART_IDS = ("scout-tokens", "scout-cost")
_CHART_ALIASES = {"task-tokens": "scout-tokens", "task-cost": "scout-cost"}
CHART_IDS = DEFAULT_CHART_IDS + EXTRA_CHART_IDS
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
        "scout": empty_scout(),
    }


def empty_scout() -> dict[str, Any]:
    return {
        "provider": "openai",
        "model": SCOUT_DEFAULT_MODELS["openai"],
        "models": {},
        "base_url": "",
        "bedrock_region": SCOUT_DEFAULT_BEDROCK_REGION,
        "bedrock_model": "",
        "tools": list(SCOUT_TOOLS),
        "auto": list(SCOUT_AUTO_DEFAULT),
        "tools_version": SCOUT_TOOLS_VERSION,
        "context": "",
        "max_tokens": SCOUT_DEFAULT_TOKENS,
        "duration_sec": SCOUT_DEFAULT_DURATION,
        "mcps": [],
    }


def default_charts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    x = 0
    y = 0
    for chart_id in DEFAULT_CHART_IDS:
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
        chart_id = _CHART_ALIASES.get(str(item.get("id") or "").strip(), str(item.get("id") or "").strip())
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
    raw_scout = raw.get("scout")
    if not isinstance(raw_scout, dict):
        raw_scout = raw.get("tasks")
    data["scout"] = _clean_scout(raw_scout)
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
        "scout": public_scout(cleaned),
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
    scout_patch = patch.get("scout") if isinstance(patch.get("scout"), dict) else None
    if scout_patch is None and isinstance(patch.get("tasks"), dict):
        scout_patch = patch["tasks"]
    if scout_patch is not None:
        incoming = dict(scout_patch)
        merged = dict(current.get("scout") or empty_scout())
        models = _merge_scout_models(merged.get("models"), incoming.pop("models", None))
        next_provider = str(incoming.get("provider") or merged.get("provider") or "openai")
        if next_provider not in SCOUT_PROVIDERS:
            next_provider = str(merged.get("provider") or "openai")
        if "model" in incoming:
            text = _clip_scout_model(incoming.get("model"))
            if text:
                models[next_provider] = text
        if "bedrock_model" in incoming:
            text = _clip_scout_model(incoming.get("bedrock_model"))
            if text:
                models["bedrock"] = text
        for key in ("provider", "base_url", "bedrock_region", "context"):
            if key in incoming:
                merged[key] = incoming[key]
        for key in ("tools", "auto", "max_tokens", "duration_sec", "tools_version"):
            if key in incoming:
                merged[key] = incoming[key]
        if "mcps" in incoming:
            merged["mcps"] = _keep_mcp_env(merged.get("mcps"), incoming.get("mcps"))
        merged["models"] = models
        current["scout"] = merged
        current.pop("tasks", None)
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


def _clip_scout_model(value: Any) -> str:
    return str(value or "").strip()[:120]


def _merge_scout_models(current: Any, incoming: Any) -> dict[str, str]:
    models: dict[str, str] = {}
    for source in (current, incoming):
        if not isinstance(source, dict):
            continue
        for key in SCOUT_PROVIDERS:
            if key not in source:
                continue
            text = _clip_scout_model(source.get(key))
            if text:
                models[key] = text
    return models


def _clean_scout(raw: Any) -> dict[str, Any]:
    data = empty_scout()
    if not isinstance(raw, dict):
        return data
    provider = str(raw.get("provider") or "").strip()
    if provider in SCOUT_PROVIDERS:
        data["provider"] = provider
    models = _merge_scout_models(raw.get("models"), None)
    if not models:
        legacy = _clip_scout_model(raw.get("model"))
        if legacy:
            models[data["provider"]] = legacy
        bedrock = _clip_scout_model(raw.get("bedrock_model"))
        if bedrock:
            models["bedrock"] = bedrock
    data["models"] = models
    data["model"] = models.get(data["provider"]) or SCOUT_DEFAULT_MODELS[data["provider"]]
    data["bedrock_model"] = models.get("bedrock") or ""
    data["base_url"] = str(raw.get("base_url") or "").strip()[:200]
    region = str(raw.get("bedrock_region") or "").strip()[:40]
    if region:
        data["bedrock_region"] = region
    data["tools"] = _clean_scout_tools(raw.get("tools"), SCOUT_TOOLS)
    version = _scout_tools_version(raw.get("tools_version"))
    if version < SCOUT_TOOLS_VERSION:
        if isinstance(raw.get("tools"), list) and set(data["tools"]) == set(_LEGACY_SCOUT_TOOLS):
            data["tools"] = list(SCOUT_TOOLS)
        elif set(data["tools"]) == _PRE_WEATHER_TOOLS:
            data["tools"] = list(SCOUT_TOOLS)
        elif "weather" not in data["tools"]:
            core = _tool_core(data["tools"])
            if core == set(_LEGACY_SCOUT_TOOLS):
                data["tools"] = _insert_tool(data["tools"], "search", "weather")
                data["tools"] = _insert_tool(data["tools"], "weather", "open_page")
            elif core == _PRE_WEATHER_TOOLS:
                data["tools"] = _insert_tool(data["tools"], "search", "weather")
        data["tools_version"] = SCOUT_TOOLS_VERSION
    else:
        data["tools_version"] = version
    data["auto"] = _clean_scout_tools(raw.get("auto"), SCOUT_AUTO_DEFAULT)
    if version < SCOUT_TOOLS_VERSION:
        if set(data["auto"]) == {"search", "fetch"} and "open_page" in data["tools"]:
            data["auto"] = list(SCOUT_AUTO_DEFAULT)
        elif set(data["auto"]) == _PRE_WEATHER_AUTO and "weather" in data["tools"]:
            data["auto"] = list(SCOUT_AUTO_DEFAULT)
        elif "weather" in data["tools"] and "weather" not in data["auto"]:
            auto_core = _tool_core(data["auto"])
            if auto_core in ({"search", "fetch"}, _PRE_WEATHER_AUTO):
                data["auto"] = _insert_tool(data["auto"], "search", "weather")
    data["auto"] = [name for name in data["auto"] if name in data["tools"]]
    data["context"] = str(raw.get("context") or "").strip()[:4000]
    data["max_tokens"] = _clean_choice(raw.get("max_tokens"), SCOUT_TOKEN_LIMITS, SCOUT_DEFAULT_TOKENS)
    data["duration_sec"] = _clean_choice(raw.get("duration_sec"), SCOUT_DURATION_LIMITS, SCOUT_DEFAULT_DURATION)
    data["mcps"] = _clean_scout_mcps(raw.get("mcps"))
    return data


def _clean_choice(raw: Any, allowed: tuple[int, ...], default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value in allowed else default


def _scout_tools_version(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _tool_core(names: list[str]) -> set[str]:
    return {name for name in names if name != "capture_screen"}


def _insert_tool(names: list[str], after: str, add: str) -> list[str]:
    if add in names:
        return names
    out: list[str] = []
    for name in names:
        out.append(name)
        if name == after:
            out.append(add)
    if add not in out:
        out.append(add)
    return out


def _clean_scout_tools(raw: Any, fallback: tuple[str, ...]) -> list[str]:
    names = set(SCOUT_TOOL_CATALOG)
    if not isinstance(raw, list):
        return list(fallback)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if name not in names or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _clean_scout_mcps(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        mcp_id = str(item.get("id") or "").strip()[:24]
        if not mcp_id or mcp_id in seen:
            continue
        transport = str(item.get("transport") or "stdio").strip()
        if transport not in {"stdio", "http"}:
            transport = "stdio"
        seen.add(mcp_id)
        row = {
            "id": mcp_id,
            "name": str(item.get("name") or mcp_id).strip()[:80],
            "transport": transport,
            "command": str(item.get("command") or "").strip()[:240],
            "args": str(item.get("args") or "").strip()[:400],
            "url": str(item.get("url") or "").strip()[:400],
            "auto": bool(item.get("auto")),
            "enabled": item.get("enabled") is not False,
        }
        env = _clean_mcp_env(item.get("env"))
        if env:
            row["env"] = env
        out.append(row)
        if len(out) >= 8:
            break
    return out


def _clean_mcp_env(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip()[:80]
        if not name or name in out:
            continue
        out[name] = str(value)[:400]
        if len(out) >= 16:
            break
    return out


def _keep_mcp_env(current: Any, incoming: Any) -> list[Any]:
    if not isinstance(incoming, list):
        return []
    old: dict[str, dict[str, Any]] = {}
    if isinstance(current, list):
        for item in current:
            if isinstance(item, dict) and item.get("id"):
                old[str(item.get("id"))] = item
    out: list[Any] = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        mcp_id = str(row.get("id") or "")
        if not row.get("env") and mcp_id in old and old[mcp_id].get("env"):
            row["env"] = old[mcp_id]["env"]
        out.append(row)
    return out


def _public_mcp(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    env = row.pop("env", None)
    row["has_env"] = bool(env)
    return row


def public_scout(data: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = validate_settings(data if data is not None else load_settings())
    scout = dict(cleaned.get("scout") or empty_scout())
    provider = str(scout.get("provider") or "openai")
    from sonoscribe.lock import lock_enabled
    from sonoscribe.scout.keys import has_scout_key

    return {
        "provider": provider,
        "model": scout.get("model") or SCOUT_DEFAULT_MODELS.get(provider, ""),
        "models": dict(scout.get("models") or {}),
        "base_url": scout.get("base_url") or "",
        "bedrock_region": scout.get("bedrock_region") or SCOUT_DEFAULT_BEDROCK_REGION,
        "bedrock_model": scout.get("bedrock_model") or "",
        "tools": list(scout.get("tools") or SCOUT_TOOLS),
        "auto": list(scout.get("auto") or SCOUT_AUTO_DEFAULT),
        "context": str(scout.get("context") or ""),
        "max_tokens": _clean_choice(scout.get("max_tokens"), SCOUT_TOKEN_LIMITS, SCOUT_DEFAULT_TOKENS),
        "duration_sec": _clean_choice(scout.get("duration_sec"), SCOUT_DURATION_LIMITS, SCOUT_DEFAULT_DURATION),
        "mcps": [_public_mcp(item) for item in scout.get("mcps") or [] if isinstance(item, dict)],
        "has_key": has_scout_key(provider),
        "lock_ok": lock_enabled(),
        "providers": list(SCOUT_PROVIDERS),
        "default_models": dict(SCOUT_DEFAULT_MODELS),
        "default_base_url": SCOUT_DEFAULT_BASE_URL,
        "tool_catalog": [
            {"id": "search", "label": "search", "hint": "public web"},
            {"id": "weather", "label": "weather", "hint": "wttr.in place"},
            {"id": "fetch", "label": "fetch", "hint": "a public page"},
            {"id": "open_page", "label": "browser", "hint": "queue a site"},
            {"id": "run_script", "label": "script", "hint": "bash or applescript"},
            {"id": "write_file", "label": "write file", "hint": "under home"},
            {"id": "read_file", "label": "read file", "hint": "under home"},
            {"id": "capture_screen", "label": "screen", "hint": "opt in, current display"},
        ],
        "token_limits": list(SCOUT_TOKEN_LIMITS),
        "duration_limits": list(SCOUT_DURATION_LIMITS),
    }


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
