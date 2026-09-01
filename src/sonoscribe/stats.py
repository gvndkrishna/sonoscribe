"""Persisted dictation and command stats."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ENV_STATS = "SONOSCRIBE_STATS"
_MAX_ACTIVITY = 50


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
    }


def average_wpm(stats: dict[str, Any]) -> float:
    seconds = float(stats.get("dictation_seconds") or 0)
    words = int(stats.get("dictation_words") or 0)
    if seconds <= 0 or words <= 0:
        return 0.0
    return words / seconds * 60.0


def count_words(text: str) -> int:
    return len(text.split())


def public_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "dictation_words": int(stats.get("dictation_words") or 0),
        "dictation_seconds": round(float(stats.get("dictation_seconds") or 0), 2),
        "command_runs": int(stats.get("command_runs") or 0),
        "routine_runs": int(stats.get("routine_runs") or 0),
        "average_wpm": round(average_wpm(stats), 1),
        "activity": list(stats.get("activity") or []),
    }


class StatsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or stats_path()
        self._lock = threading.Lock()
        self._data = empty_stats()
        self._load()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return public_stats(self._data)

    def record_dictation(self, text: str, seconds: float) -> None:
        words = count_words(text)
        if words <= 0 and seconds <= 0:
            return
        self._update(
            dictation_words=words,
            dictation_seconds=max(0.0, seconds),
            kind="dictate",
            label=f"{words} word" if words == 1 else f"{words} words",
        )

    def record_command(self, label: str) -> None:
        self._update(command_runs=1, kind="command", label=label)

    def record_routine(self, label: str) -> None:
        self._update(routine_runs=1, kind="routine", label=label)

    def _update(
        self,
        *,
        kind: str,
        label: str,
        dictation_words: int = 0,
        dictation_seconds: float = 0.0,
        command_runs: int = 0,
        routine_runs: int = 0,
    ) -> None:
        event = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
        }
        with self._lock:
            self._data["dictation_words"] = int(self._data["dictation_words"]) + dictation_words
            self._data["dictation_seconds"] = float(self._data["dictation_seconds"]) + dictation_seconds
            self._data["command_runs"] = int(self._data["command_runs"]) + command_runs
            self._data["routine_runs"] = int(self._data["routine_runs"]) + routine_runs
            activity = list(self._data.get("activity") or [])
            activity.insert(0, event)
            self._data["activity"] = activity[:_MAX_ACTIVITY]
            self._save_locked()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        base = empty_stats()
        for key in ("dictation_words", "command_runs", "routine_runs"):
            try:
                base[key] = int(data.get(key) or 0)
            except (TypeError, ValueError):
                pass
        try:
            base["dictation_seconds"] = float(data.get("dictation_seconds") or 0)
        except (TypeError, ValueError):
            pass
        activity = data.get("activity")
        if isinstance(activity, list):
            base["activity"] = [item for item in activity if isinstance(item, dict)][:_MAX_ACTIVITY]
        self._data = base

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
