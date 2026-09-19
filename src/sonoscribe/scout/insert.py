"""Spoken insert phrasing and pasteable brief text."""

from __future__ import annotations

import re
from typing import Any

INSERT_LIMIT = 4000
_AUTO_TAIL = re.compile(
    r"(?i)(?:(?:,|\.)?\s+)?(?:and\s+)?(?:just\s+)?(?:insert|paste)\s+(?:it|that)(?:\s+please)?\s*[.!?]*\s*$"
)
_LEAD_SKILL = re.compile(r"(?i)^(?:please\s+)?insert(?:\s+this)?(?:\s+|$)")


def parse_insert_ask(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    auto = bool(_AUTO_TAIL.search(raw))
    lead = bool(_LEAD_SKILL.match(raw))
    cleaned = _AUTO_TAIL.sub("", raw).strip(" ,")
    cleaned = _LEAD_SKILL.sub("", cleaned).strip(" ,")
    return {"prompt": cleaned, "auto_insert": auto, "want_insert": auto or lead}


def clean_insert_text(raw: Any) -> str:
    return str(raw or "").strip()[:INSERT_LIMIT]


def clean_frontmost(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    bundle = str(raw.get("bundle_id") or "").strip()[:160]
    name = str(raw.get("name") or "").strip()[:80]
    if not bundle and not name:
        return {}
    return {"bundle_id": bundle, "name": name}


def insert_text_from_answer(answer: Any) -> str:
    data = answer if isinstance(answer, dict) else {}
    explicit = clean_insert_text(data.get("insert"))
    if explicit:
        return explicit
    lead = ""
    code = ""
    for block in data.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type") or "")
        text = str(block.get("text") or "").strip()
        if kind == "lead" and text and not lead:
            lead = text
        elif kind == "code" and text and not code:
            code = text
    if lead:
        return lead[:INSERT_LIMIT]
    if code:
        return code[:INSERT_LIMIT]
    from sonoscribe.scout.render import answer_plain

    return answer_plain(data, limit=INSERT_LIMIT)


def insert_text_from_run(run: dict[str, Any] | None) -> str:
    data = run if isinstance(run, dict) else {}
    stored = clean_insert_text(data.get("insert_text"))
    if stored:
        return stored
    return insert_text_from_answer(data.get("answer"))


def asked_to_insert(run: dict[str, Any] | None) -> bool:
    data = run if isinstance(run, dict) else {}
    return bool(data.get("want_insert") or data.get("auto_insert"))


def can_insert(run: dict[str, Any] | None) -> bool:
    data = run if isinstance(run, dict) else {}
    if str(data.get("status") or "") != "done" or not asked_to_insert(data):
        return False
    return bool(insert_text_from_run(data))


def notice_shows_insert(run: dict[str, Any] | None) -> bool:
    data = run if isinstance(run, dict) else {}
    if data.get("auto_insert"):
        return False
    return can_insert(data)


def notice_holds_bubble(run: dict[str, Any] | None) -> bool:
    from sonoscribe.notify import notice_status

    return notice_shows_insert(run) or notice_status(run) == "needs_confirm"


def needs_restore_app(saved: dict[str, str] | None, current: dict[str, str] | None) -> bool:
    wanted = str((saved or {}).get("bundle_id") or "").strip()
    if not wanted:
        return False
    here = str((current or {}).get("bundle_id") or "").strip()
    return bool(here) and here != wanted


def activate_frontmost(frontmost: dict[str, str] | None) -> bool:
    bundle = str((frontmost or {}).get("bundle_id") or "").strip()
    if not bundle:
        return False
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication
    except Exception:
        return False
    try:
        apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle)
    except Exception:
        return False
    if not apps:
        return False
    try:
        return bool(apps[0].activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
    except Exception:
        return False
