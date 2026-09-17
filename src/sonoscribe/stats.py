"""Persisted dictation and command stats."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ENV_STATS = "SONOSCRIBE_STATS"
_MAX_ACTIVITY = 200
_COMMAND_TYPES = ("keyboard", "website", "app", "file", "system", "script", "text")
USAGE_WEEKS = 16


def stats_path() -> Path:
    override = os.environ.get(_ENV_STATS)
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Sonoscribe" / "stats.json"


def empty_stats() -> dict[str, Any]:
    return {
        "dictation_words": 0,
        "dictation_seconds": 0.0,
        "command_runs": 0,
        "routine_runs": 0,
        "activity": [],
        "updated_at": None,
    }


def clean_stats_blob(raw: Any) -> dict[str, Any]:
    blob = empty_stats()
    if not isinstance(raw, dict):
        return blob
    for key in ("dictation_words", "command_runs", "routine_runs"):
        try:
            blob[key] = int(raw.get(key) or 0)
        except (TypeError, ValueError):
            pass
    try:
        blob["dictation_seconds"] = float(raw.get("dictation_seconds") or 0)
    except (TypeError, ValueError):
        pass
    activity = raw.get("activity")
    if isinstance(activity, list):
        blob["activity"] = [item for item in activity if isinstance(item, dict)][:_MAX_ACTIVITY]
    stamp = raw.get("updated_at")
    blob["updated_at"] = str(stamp) if stamp else None
    return blob


def merge_stats_blobs(left: Any, right: Any) -> dict[str, Any]:
    first = clean_stats_blob(left)
    second = clean_stats_blob(right)
    seen: set[tuple[str, str, str, str]] = set()
    activity: list[dict[str, Any]] = []
    for item in list(first.get("activity") or []) + list(second.get("activity") or []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("at") or ""),
            str(item.get("kind") or ""),
            str(item.get("label") or ""),
            str(item.get("command_type") or ""),
            str(item.get("model") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        activity.append(item)
    activity.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    updated = first.get("updated_at")
    other = second.get("updated_at")
    if other and (not updated or str(other) > str(updated)):
        updated = other
    return {
        "dictation_words": max(int(first["dictation_words"]), int(second["dictation_words"])),
        "dictation_seconds": max(float(first["dictation_seconds"]), float(second["dictation_seconds"])),
        "command_runs": max(int(first["command_runs"]), int(second["command_runs"])),
        "routine_runs": max(int(first["routine_runs"]), int(second["routine_runs"])),
        "activity": activity[:_MAX_ACTIVITY],
        "updated_at": updated,
    }


def average_wpm(stats: dict[str, Any]) -> float:
    seconds = float(stats.get("dictation_seconds") or 0)
    words = int(stats.get("dictation_words") or 0)
    if seconds <= 0 or words <= 0:
        return 0.0
    return words / seconds * 60.0


def count_words(text: str) -> int:
    return len(text.split())


def resolve_zone(name: str | None):
    if not name or name == "local":
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now().astimezone().tzinfo


def public_stats(stats: dict[str, Any], tz=None, model_labels: dict[str, str] | None = None) -> dict[str, Any]:
    activity = list(stats.get("activity") or [])[:_MAX_ACTIVITY]
    return {
        "dictation_words": int(stats.get("dictation_words") or 0),
        "dictation_seconds": round(float(stats.get("dictation_seconds") or 0), 2),
        "command_runs": int(stats.get("command_runs") or 0),
        "routine_runs": int(stats.get("routine_runs") or 0),
        "average_wpm": round(average_wpm(stats), 1),
        "activity": activity,
        "charts": chart_series(activity, tz=tz, model_labels=model_labels),
    }


def chart_series(activity: list[Any], tz=None, model_labels: dict[str, str] | None = None) -> dict[str, Any]:
    zone = tz or datetime.now().astimezone().tzinfo
    labels = model_labels or {}
    by_kind = {"dictate": 0, "command": 0, "routine": 0}
    top: dict[str, int] = {}
    top_routines: dict[str, int] = {}
    by_model_counts: dict[str, int] = {}
    wpm_acc: dict[str, dict[str, float]] = {}
    hourly = [0] * 24
    today = datetime.now(zone).date()
    days = [(today - timedelta(days=offset)).isoformat() for offset in range(13, -1, -1)]
    daily = {day: {"dictate": 0, "command": 0, "routine": 0} for day in days}
    for item in activity:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        if kind in by_kind:
            by_kind[kind] += 1
        label = str(item.get("label") or "").strip()
        if kind == "command" and label:
            top[label] = top.get(label, 0) + 1
        if kind == "routine" and label:
            top_routines[label] = top_routines.get(label, 0) + 1
        model = str(item.get("model") or "").strip()
        if model:
            by_model_counts[model] = by_model_counts.get(model, 0) + 1
        if kind == "dictate" and model:
            bucket = wpm_acc.setdefault(model, {"words": 0.0, "seconds": 0.0})
            try:
                bucket["words"] += float(item.get("words") or 0)
            except (TypeError, ValueError):
                pass
            try:
                bucket["seconds"] += float(item.get("seconds") or 0)
            except (TypeError, ValueError):
                pass
        parsed = _parse_activity_time(item.get("at"))
        if parsed is None:
            continue
        local = parsed.astimezone(zone)
        hourly[local.hour] += 1
        day = local.date().isoformat()
        if day in daily and kind in daily[day]:
            daily[day][kind] += 1
    top_commands = [
        {"label": label, "count": count}
        for label, count in sorted(top.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    ]
    routine_leaders = [
        {"label": label, "count": count}
        for label, count in sorted(top_routines.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    ]
    by_model = [
        {"id": key, "label": labels.get(key, key), "count": count}
        for key, count in sorted(by_model_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    wpm_by_model = []
    for key, bucket in sorted(wpm_acc.items(), key=lambda pair: pair[0]):
        seconds = float(bucket["seconds"])
        words = float(bucket["words"])
        if seconds <= 0 or words <= 0:
            continue
        wpm_by_model.append(
            {
                "id": key,
                "label": labels.get(key, key),
                "wpm": round(words / seconds * 60.0, 1),
                "words": int(words),
            }
        )
    wpm_by_model.sort(key=lambda item: (-item["wpm"], item["label"]))
    by_command_type = {key: 0 for key in _COMMAND_TYPES}
    for item in activity:
        if not isinstance(item, dict) or str(item.get("kind") or "") != "command":
            continue
        cmd_type = str(item.get("command_type") or "").strip()
        if cmd_type in by_command_type:
            by_command_type[cmd_type] += 1
    return {
        "by_kind": by_kind,
        "versus": {"dictate": by_kind["dictate"], "command": by_kind["command"]},
        "versus_routines": {"command": by_kind["command"], "routine": by_kind["routine"]},
        "by_command_type": by_command_type,
        "by_model": by_model,
        "wpm_by_model": wpm_by_model,
        "daily": [{"day": day, **daily[day]} for day in days],
        "hourly": hourly,
        "top_commands": top_commands,
        "top_routines": routine_leaders,
        "usage": _usage_series(activity, zone),
    }


def _is_model_use(item: dict[str, Any]) -> bool:
    if str(item.get("kind") or "") == "dictate":
        return True
    return bool(str(item.get("model") or "").strip())


def _usage_series(activity: list[Any], zone, weeks: int = USAGE_WEEKS) -> list[dict[str, Any]]:
    today = datetime.now(zone).date()
    sunday0 = (today.weekday() + 1) % 7
    start = today - timedelta(days=sunday0 + 7 * (weeks - 1))
    days = [(start + timedelta(days=offset)).isoformat() for offset in range(weeks * 7)]
    counts = {day: 0 for day in days}
    for item in activity:
        if not isinstance(item, dict) or not _is_model_use(item):
            continue
        parsed = _parse_activity_time(item.get("at"))
        if parsed is None:
            continue
        day = parsed.astimezone(zone).date().isoformat()
        if day in counts:
            counts[day] += 1
    return [{"day": day, "count": counts[day]} for day in days]


def _parse_activity_time(raw: Any) -> datetime | None:
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


class StatsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or stats_path()
        self._lock = threading.Lock()
        self._data = empty_stats()
        self._remotes: dict[str, dict[str, Any]] = {}
        self._stamp: tuple[int, int] | None = None
        self._load()

    def snapshot(self, device_id: str | None = None) -> dict[str, Any]:
        from sonoscribe.device import this_device
        from sonoscribe.settings import load_settings, sync_what

        settings = load_settings()
        zone = resolve_zone(settings.get("timezone"))
        this = this_device(settings)
        roster = settings.get("devices") or [this]
        what = sync_what(settings)
        stats_on = bool(settings.get("sync", {}).get("enabled")) and bool(what.get("stats"))
        chosen = str(device_id or "").strip() or this["id"]
        from sonoscribe.transcriber import MODEL_LABELS

        model_labels = dict(MODEL_LABELS)
        for item in settings.get("custom_models") or []:
            if isinstance(item, dict) and item.get("id"):
                model_labels[str(item["id"])] = str(item.get("name") or item["id"])
        with self._lock:
            self._reload_locked()
            remotes = dict(self._remotes)
            if chosen != this["id"]:
                blob = remotes.get(chosen) or empty_stats()
                public = public_stats(blob, tz=zone, model_labels=model_labels)
            else:
                public = public_stats(self._data, tz=zone, model_labels=model_labels)
                chosen = this["id"]
        public["device_id"] = chosen
        public["stats_synced"] = stats_on
        seen: set[str] = set()
        devices: list[dict[str, Any]] = []
        for item in roster:
            device_id = str(item.get("id") or "")
            if not device_id or device_id in seen:
                continue
            seen.add(device_id)
            devices.append(
                {
                    "id": device_id,
                    "name": str(item.get("name") or "Mac"),
                    "this": device_id == this["id"],
                }
            )
        if stats_on:
            for device_id in remotes:
                if device_id in seen:
                    continue
                seen.add(device_id)
                devices.append({"id": device_id, "name": "Mac", "this": device_id == this["id"]})
        public["devices"] = devices
        return public

    def export_blob(self) -> dict[str, Any]:
        with self._lock:
            self._reload_locked()
            return clean_stats_blob(self._data)

    def remote_devices(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            self._reload_locked()
            return {key: clean_stats_blob(value) for key, value in self._remotes.items()}

    def apply_synced_stats(self, stats_by_device: dict[str, Any], this_id: str) -> None:
        with self._lock:
            self._reload_locked()
            remotes: dict[str, dict[str, Any]] = {}
            mine = clean_stats_blob(self._data)
            for key, value in (stats_by_device or {}).items():
                device_id = str(key or "").strip()
                if not device_id or not isinstance(value, dict):
                    continue
                blob = clean_stats_blob(value)
                if device_id == this_id:
                    mine = merge_stats_blobs(mine, blob)
                else:
                    remotes[device_id] = blob
            self._data = mine
            self._remotes = remotes
            self._save_locked()

    def record_dictation(self, text: str, seconds: float, model: str = "") -> None:
        words = count_words(text)
        if words <= 0 and seconds <= 0:
            return
        self._update(
            dictation_words=words,
            dictation_seconds=max(0.0, seconds),
            kind="dictate",
            label=f"{words} word" if words == 1 else f"{words} words",
            model=model,
            words=words,
            seconds=max(0.0, seconds),
        )

    def record_command(self, label: str, command_type: str = "", model: str = "") -> None:
        self._update(command_runs=1, kind="command", label=label, command_type=command_type, model=model)

    def record_routine(self, label: str, model: str = "") -> None:
        self._update(routine_runs=1, kind="routine", label=label, model=model)

    def _update(
        self,
        *,
        kind: str,
        label: str,
        dictation_words: int = 0,
        dictation_seconds: float = 0.0,
        command_runs: int = 0,
        routine_runs: int = 0,
        command_type: str = "",
        model: str = "",
        words: int = 0,
        seconds: float = 0.0,
    ) -> None:
        from sonoscribe.settings import load_settings

        if load_settings().get("private_mode"):
            return
        event = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
        }
        cleaned_type = str(command_type or "").strip()
        if kind == "command" and cleaned_type in _COMMAND_TYPES:
            event["command_type"] = cleaned_type
        cleaned_model = str(model or "").strip()
        if cleaned_model:
            event["model"] = cleaned_model
        if kind == "dictate":
            if words:
                event["words"] = int(words)
            if seconds:
                event["seconds"] = round(float(seconds), 3)
        with self._lock:
            self._reload_locked()
            self._data["dictation_words"] = int(self._data["dictation_words"]) + dictation_words
            self._data["dictation_seconds"] = float(self._data["dictation_seconds"]) + dictation_seconds
            self._data["command_runs"] = int(self._data["command_runs"]) + command_runs
            self._data["routine_runs"] = int(self._data["routine_runs"]) + routine_runs
            activity = list(self._data.get("activity") or [])
            activity.insert(0, event)
            self._data["activity"] = activity[:_MAX_ACTIVITY]
            self._data["updated_at"] = event["at"]
            self._save_locked()

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _reload_locked(self) -> None:
        stamp = self._file_stamp()
        if stamp is not None and stamp == self._stamp:
            return
        self._load()

    def _load(self) -> None:
        self._data = empty_stats()
        self._remotes = {}
        self._stamp = self._file_stamp()
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self._data = clean_stats_blob(data)
        remotes = data.get("devices")
        if isinstance(remotes, dict):
            cleaned: dict[str, dict[str, Any]] = {}
            for key, value in remotes.items():
                device_id = str(key or "").strip()
                if device_id and isinstance(value, dict):
                    cleaned[device_id] = clean_stats_blob(value)
            self._remotes = cleaned
        self._stamp = self._file_stamp()

    def _save_locked(self) -> None:
        payload = dict(clean_stats_blob(self._data))
        payload["devices"] = {key: clean_stats_blob(value) for key, value in self._remotes.items()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._stamp = self._file_stamp()
