"""Local scout run history. Never synced."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sonoscribe.catalog import support_dir

_ENV_SCOUT = "SONOSCRIBE_SCOUT"
_ENV_LEGACY = "SONOSCRIBE_TASKS"
_MAX_RUNS = 50
_MAX_TURNS = 8
_ACTIVE = ("thinking", "tool", "needs_confirm")
_BRIEF_KEEP = timedelta(days=10)
_ERROR_KEEP = timedelta(days=1)
_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_path: Path | None = None


def scout_path() -> Path:
    override = os.environ.get(_ENV_SCOUT) or os.environ.get(_ENV_LEGACY)
    if override:
        return Path(override)
    return support_dir() / "scout.json"


def _read_path() -> Path:
    target = scout_path()
    if target.exists() or os.environ.get(_ENV_SCOUT) or os.environ.get(_ENV_LEGACY):
        return target
    legacy = support_dir() / "tasks.json"
    return legacy if legacy.is_file() else target


def empty_store() -> dict[str, Any]:
    return {"runs": [], "active_id": "", "continue_id": ""}


def new_run_id() -> str:
    return f"tsk-{uuid.uuid4().hex[:10]}"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clear_scout_cache() -> None:
    global _cache, _cache_path
    with _lock:
        _cache = None
        _cache_path = None


def load_store() -> dict[str, Any]:
    target = _read_path().resolve()
    with _lock:
        return _load_locked(target)


def save_store(store: dict[str, Any]) -> dict[str, Any]:
    global _cache, _cache_path
    cleaned = clean_store(store)
    target = scout_path().resolve()
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")
        _cache = cleaned
        _cache_path = target
        return cleaned


def clean_store(raw: Any) -> dict[str, Any]:
    data = empty_store()
    if not isinstance(raw, dict):
        return data
    runs: list[dict[str, Any]] = []
    for item in raw.get("runs") or []:
        cleaned = clean_run(item)
        if cleaned:
            runs.append(cleaned)
    runs = _purge_runs(runs)[:_MAX_RUNS]
    active = str(raw.get("active_id") or "")
    if active and not any(item.get("id") == active for item in runs):
        active = ""
    cont = str(raw.get("continue_id") or "").strip()
    if cont and (
        not any(item.get("id") == cont and item.get("status") not in _ACTIVE for item in runs)
    ):
        cont = ""
    data["runs"] = runs
    data["active_id"] = active
    data["continue_id"] = cont
    return data


def clean_run(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    run_id = str(raw.get("id") or "").strip() or new_run_id()
    status = str(raw.get("status") or "error").strip()
    if status not in {
        "thinking",
        "tool",
        "needs_confirm",
        "done",
        "error",
        "cancelled",
    }:
        status = "error"
    prompt = str(raw.get("prompt") or "").strip()[:500]
    answer = _clean_answer(raw.get("answer"))
    title = str(raw.get("title") or "").strip()[:80]
    if not title and isinstance(answer, dict):
        title = str(answer.get("title") or "").strip()[:80]
    if not title:
        title = default_title(prompt)
    follow_up = str(raw.get("follow_up") or "").strip()[:500]
    error = str(raw.get("error") or "")[:400]
    confirm = raw.get("confirm") if isinstance(raw.get("confirm"), dict) else None
    turns = _clean_turns(raw.get("turns"))
    if not turns:
        turns = seed_turns(
            {
                "prompt": prompt,
                "follow_up": follow_up,
                "answer": answer,
                "status": status,
                "error": error,
                "confirm": confirm,
            }
        )
    if not follow_up and len(turns) > 1:
        follow_up = str(turns[-1].get("prompt") or "").strip()[:500]
    if answer is None:
        for item in reversed(turns):
            if item.get("answer"):
                answer = item.get("answer")
                break
    created = str(raw.get("created_at") or iso_now())
    updated = str(raw.get("updated_at") or created)
    from sonoscribe.scout.insert import clean_frontmost, clean_insert_text, insert_text_from_answer

    insert_text = clean_insert_text(raw.get("insert_text")) or insert_text_from_answer(answer)
    return {
        "id": run_id,
        "created_at": created,
        "updated_at": updated,
        "title": title,
        "prompt": prompt,
        "follow_up": follow_up,
        "status": status,
        "tool_name": str(raw.get("tool_name") or ""),
        "steps": [item for item in (raw.get("steps") or []) if isinstance(item, dict)][:40],
        "confirm": confirm,
        "open_url": _clean_open_url(raw.get("open_url")),
        "answer": answer,
        "error": error,
        "turns": turns,
        "insert_text": insert_text,
        "auto_insert": bool(raw.get("auto_insert")),
        "want_insert": bool(raw.get("want_insert") or raw.get("auto_insert")),
        "frontmost": clean_frontmost(raw.get("frontmost")),
    }


def public_run(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at") or run.get("created_at"),
        "title": run_title(run),
        "prompt": run.get("prompt"),
        "follow_up": run.get("follow_up") or "",
        "status": run.get("status"),
        "tool_name": run.get("tool_name") or "",
        "steps": list(run.get("steps") or []),
        "confirm": run.get("confirm"),
        "open_url": run.get("open_url") or "",
        "answer": run.get("answer"),
        "error": run.get("error") or "",
        "turns": list(run.get("turns") or []),
        "insert_text": _public_insert_text(run),
        "auto_insert": bool(run.get("auto_insert")),
        "want_insert": bool(run.get("want_insert") or run.get("auto_insert")),
        "frontmost": dict(run.get("frontmost") or {}) if isinstance(run.get("frontmost"), dict) else {},
    }


def _public_insert_text(run: dict[str, Any]) -> str:
    from sonoscribe.scout.insert import insert_text_from_run

    return insert_text_from_run(run)


def seed_turns(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = run if isinstance(run, dict) else {}
    prompt = str(data.get("prompt") or "").strip()[:500]
    follow = str(data.get("follow_up") or "").strip()[:500]
    answer = data.get("answer") if isinstance(data.get("answer"), dict) else None
    status = str(data.get("status") or "done")
    if status not in {
        "thinking",
        "tool",
        "needs_confirm",
        "done",
        "error",
        "cancelled",
    }:
        status = "done"
    error = str(data.get("error") or "")[:400]
    confirm = data.get("confirm") if isinstance(data.get("confirm"), dict) else None
    turns: list[dict[str, Any]] = []
    first = {
        "prompt": prompt,
        "answer": None if follow else answer,
        "status": "done" if follow else status,
        "error": "" if follow else error,
        "confirm": None if follow else confirm,
    }
    if first["prompt"] or first["answer"] or first["error"]:
        turns.append(first)
    if follow:
        turns.append(
            {
                "prompt": follow,
                "answer": answer,
                "status": status,
                "error": error,
                "confirm": confirm,
            }
        )
    return _cap_turns(turns)


def run_turns(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = run if isinstance(run, dict) else {}
    turns = _clean_turns(data.get("turns"))
    return turns or seed_turns(data)


def append_follow_up_turn(run: dict[str, Any], prompt: str) -> list[dict[str, Any]]:
    turns = [item for item in run_turns(run) if item.get("status") not in _ACTIVE]
    pending = {
        "prompt": str(prompt or "").strip()[:500],
        "answer": None,
        "status": "thinking",
        "error": "",
        "confirm": None,
    }
    turns.append(pending)
    return _cap_turns(turns)


def _clean_turns(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    turns: list[dict[str, Any]] = []
    for item in raw:
        cleaned = _clean_turn(item)
        if cleaned:
            turns.append(cleaned)
    return _cap_turns(turns)


def _clean_open_url(raw: Any) -> str:
    from sonoscribe.scout.tools import public_http_url

    return public_http_url(raw)


def get_run(run_id: str, store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ident = str(run_id or "").strip()
    if not ident:
        return None
    data = store if store is not None else load_store()
    for item in data.get("runs") or []:
        if isinstance(item, dict) and item.get("id") == ident:
            return public_run(item)
    return None


def _clean_answer(raw: Any) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    from sonoscribe.scout.render import parse_answer

    return parse_answer(raw)


def _clean_turn(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    prompt = str(raw.get("prompt") or "").strip()[:500]
    answer = _clean_answer(raw.get("answer"))
    status = str(raw.get("status") or "done").strip()
    if status not in {
        "thinking",
        "tool",
        "needs_confirm",
        "done",
        "error",
        "cancelled",
    }:
        status = "done"
    error = str(raw.get("error") or "")[:400]
    confirm = raw.get("confirm") if isinstance(raw.get("confirm"), dict) else None
    if not prompt and not answer and not error:
        return None
    return {
        "prompt": prompt,
        "answer": answer,
        "status": status,
        "error": error,
        "confirm": confirm,
    }


def _cap_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(turns) <= _MAX_TURNS:
        return turns
    return [turns[0], *turns[-(_MAX_TURNS - 1) :]]


def history(store: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = store if store is not None else load_store()
    return _number_runs([public_run(item) for item in data.get("runs") or [] if public_run(item)])


def current_run(store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = store if store is not None else load_store()
    active = str(data.get("active_id") or "")
    if not active:
        return None
    for item in history(data):
        if item.get("id") == active:
            return item
    return None


def resolve_scout_ref(ref: int | str, store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    runs = history(store)
    try:
        value = int(ref)
    except (TypeError, ValueError):
        return None
    index = -value if value <= 0 else value - 1
    if index < 0 or index >= len(runs):
        return None
    return dict(runs[index])


def number_run(run: dict[str, Any] | None, store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not run:
        return None
    item = dict(run)
    ident = str(item.get("id") or "")
    for numbered in history(store):
        if numbered.get("id") == ident:
            item["n"] = numbered["n"]
            item["sku"] = numbered["sku"]
            return item
    item["n"] = 1
    item["sku"] = "sc–01"
    return item


def _number_runs(runs: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, run in enumerate(runs):
        if not run:
            continue
        item = dict(run)
        item["n"] = index + 1
        item["sku"] = f"sc–{index + 1:02d}"
        out.append(item)
    return out


def continue_id(store: dict[str, Any] | None = None) -> str:
    data = store if store is not None else load_store()
    return str(data.get("continue_id") or "")


def set_continue(run_id: str) -> dict[str, Any]:
    data = load_store()
    wanted = str(run_id or "").strip()
    if not wanted:
        data["continue_id"] = ""
        return save_store(data)
    for item in data.get("runs") or []:
        if item.get("id") == wanted and item.get("status") not in _ACTIVE:
            data["continue_id"] = wanted
            return save_store(data)
    data["continue_id"] = ""
    return save_store(data)


def take_continue_run() -> dict[str, Any] | None:
    data = load_store()
    wanted = str(data.get("continue_id") or "")
    if wanted:
        data["continue_id"] = ""
        data = save_store(data)
    if not wanted:
        return None
    for item in data.get("runs") or []:
        if item.get("id") == wanted and item.get("status") not in _ACTIVE:
            return dict(item)
    return None


def interrupt_stale() -> dict[str, Any]:
    data = load_store()
    changed = False
    for item in data.get("runs") or []:
        if item.get("status") in _ACTIVE:
            item["status"] = "error"
            item["error"] = "interrupted"
            item["confirm"] = None
            item["tool_name"] = ""
            turns = list(item.get("turns") or [])
            if turns:
                last = dict(turns[-1])
                last["status"] = "error"
                last["error"] = "interrupted"
                last["confirm"] = None
                turns[-1] = last
                item["turns"] = turns
            changed = True
    if changed:
        data["active_id"] = ""
        return save_store(data)
    return data


def upsert_run(run: dict[str, Any], *, active: bool | None = None) -> dict[str, Any]:
    data = load_store()
    cleaned = clean_run(run)
    if cleaned is None:
        return data
    cleaned["updated_at"] = iso_now()
    runs = [item for item in data.get("runs") or [] if item.get("id") != cleaned["id"]]
    runs.insert(0, cleaned)
    data["runs"] = runs[:_MAX_RUNS]
    if active is True:
        data["active_id"] = cleaned["id"]
    elif active is False and data.get("active_id") == cleaned["id"]:
        data["active_id"] = ""
    elif cleaned["status"] not in _ACTIVE and data.get("active_id") == cleaned["id"]:
        data["active_id"] = ""
    return save_store(data)


def default_title(prompt: str) -> str:
    text = " ".join(str(prompt or "").split()).strip()
    if not text:
        return "brief"
    if len(text) <= 48:
        return text
    return text[:47].rsplit(" ", 1)[0] or text[:48]


def run_title(run: dict[str, Any] | None) -> str:
    if not run:
        return "brief"
    title = str(run.get("title") or "").strip()
    if title:
        return title[:80]
    answer = run.get("answer") if isinstance(run.get("answer"), dict) else {}
    title = str(answer.get("title") or "").strip()
    if title:
        return title[:80]
    return default_title(str(run.get("prompt") or ""))


def set_run_title(run_id: str, title: str) -> dict[str, Any] | None:
    text = str(title or "").strip()[:80]
    if not text:
        return None
    data = load_store()
    for item in data.get("runs") or []:
        if item.get("id") == run_id:
            item["title"] = text
            item["updated_at"] = iso_now()
            save_store(data)
            return public_run(item)
    return None


def delete_runs(ids: list[str]) -> dict[str, Any]:
    wanted = {str(item).strip() for item in ids if str(item).strip()}
    if not wanted:
        return load_store()
    data = load_store()
    active = str(data.get("active_id") or "")
    kept = []
    for item in data.get("runs") or []:
        run_id = str(item.get("id") or "")
        busy = run_id == active and item.get("status") in _ACTIVE
        if run_id in wanted and not busy:
            continue
        kept.append(item)
    data["runs"] = kept
    if active and not any(item.get("id") == active for item in kept):
        data["active_id"] = ""
    cont = str(data.get("continue_id") or "")
    if cont and not any(item.get("id") == cont for item in kept):
        data["continue_id"] = ""
    return save_store(data)


def _parse_created(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _purge_runs(runs: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    kept = []
    for item in runs:
        if item.get("status") in _ACTIVE:
            kept.append(item)
            continue
        stamp = _parse_created(item.get("updated_at")) or _parse_created(item.get("created_at"))
        if stamp is None:
            kept.append(item)
            continue
        limit = _ERROR_KEEP if item.get("status") == "error" else _BRIEF_KEEP
        if moment - stamp < limit:
            kept.append(item)
    return kept


def _load_locked(target: Path) -> dict[str, Any]:
    global _cache, _cache_path
    if _cache is not None and _cache_path == target:
        return json.loads(json.dumps(_cache))
    if not target.is_file():
        _cache = empty_store()
        _cache_path = target
        return empty_store()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    cleaned = clean_store(raw)
    _cache = cleaned
    _cache_path = target
    return json.loads(json.dumps(cleaned))
