"""Copy for the menu-bar scout notice. No AppKit here."""

from __future__ import annotations

from typing import Any

from sonoscribe.scout.render import answer_blurb, clean_blurb

_NOTICE_STATUSES = frozenset({"done", "error", "needs_confirm"})
BUBBLE_SECONDS = 5
SCRIPT_PREVIEW_MAX_CHARS = 480
SCRIPT_PREVIEW_MAX_LINES = 12


def notice_status(run: dict[str, Any] | None) -> str:
    return str((run or {}).get("status") or "").strip()


def should_notice(run: dict[str, Any] | None) -> bool:
    return notice_status(run) in _NOTICE_STATUSES and bool(str((run or {}).get("id") or "").strip())


def notice_kicker(status: str) -> str:
    if status == "error":
        return "error"
    if status == "needs_confirm":
        return "confirm"
    return "scout"


def notice_title(run: dict[str, Any] | None) -> str:
    data = run if isinstance(run, dict) else {}
    title = str(data.get("title") or "").strip()
    if title:
        return title[:80]
    prompt = str(data.get("prompt") or "").strip()
    return prompt[:80] if prompt else "brief"


def notice_blurb(run: dict[str, Any] | None) -> str:
    data = run if isinstance(run, dict) else {}
    if notice_status(data) == "needs_confirm":
        confirm = data.get("confirm") if isinstance(data.get("confirm"), dict) else {}
        return clean_blurb(confirm.get("title") or confirm.get("name")) or "confirm"
    blurb = answer_blurb(data.get("answer"))
    if blurb:
        return blurb
    if notice_status(data) == "error":
        return clean_blurb(data.get("error")) or "failed"
    return clean_blurb(notice_title(data))


def notice_body(run: dict[str, Any] | None) -> str:
    return notice_blurb(run) or notice_title(run)


def notice_insert_label() -> str:
    return "insert"


def notice_dismiss_label() -> str:
    return "dismiss"


def notice_run_label() -> str:
    return "run"


def notice_cancel_label() -> str:
    return "cancel"


def notice_later_label() -> str:
    return "later"


def is_script_confirm(run: dict[str, Any] | None) -> bool:
    data = run if isinstance(run, dict) else {}
    if notice_status(data) != "needs_confirm":
        return False
    confirm = data.get("confirm") if isinstance(data.get("confirm"), dict) else {}
    return str(confirm.get("tool") or "") == "run_script"


def notice_script_body(run: dict[str, Any] | None) -> str:
    if not is_script_confirm(run):
        return ""
    confirm = (run or {}).get("confirm") if isinstance((run or {}).get("confirm"), dict) else {}
    text = str(confirm.get("preview") or "").strip()
    if not text and isinstance(confirm.get("args"), dict):
        text = str(confirm.get("args", {}).get("body") or "").strip()
    if not text:
        return ""
    lines = text.splitlines()
    if len(text) > SCRIPT_PREVIEW_MAX_CHARS or len(lines) > SCRIPT_PREVIEW_MAX_LINES:
        return ""
    return text


def reminder_kicker() -> str:
    return "scribe"


def reminder_title(note: dict[str, Any] | None) -> str:
    title = str((note or {}).get("title") or "").strip()
    return title[:80] if title else "reminder"


def reminder_done_label() -> str:
    return "done"


def notice_menu_label(run: dict[str, Any] | None) -> str:
    sku = str((run or {}).get("sku") or "").strip()
    title = notice_title(run)
    blurb = notice_blurb(run)
    body = blurb or title
    if blurb and title and blurb.casefold() not in title.casefold() and title.casefold() not in blurb.casefold():
        body = f"{title} · {blurb}"
    if sku:
        return f"{sku}  {body}"[:80]
    return body[:80]
