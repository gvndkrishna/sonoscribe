"""Paste into the focused app, or copy to the clipboard."""

from __future__ import annotations

import time
from threading import Timer

from AppKit import (
    NSData,
    NSPasteboard,
    NSPasteboardItem,
    NSPasteboardTypeString,
)
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSourceCreate,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventSourceStateCombinedSessionState,
    kCGSessionEventTap,
)

_VK_ANSI_V = 0x09
_VK_ANSI_Z = 0x06
_VK_SPACE = 0x31
_VK_DELETE = 0x33
_VK_RETURN = 0x24
_TRANSIENT = "org.nspasteboard.TransientType"
_CONCEALED = "org.nspasteboard.ConcealedType"
_NONCOALESCED = 0x000008


def insert(text: str, copy_only: bool = False) -> None:
    trimmed = text.strip()
    if not trimmed:
        return
    if copy_only:
        _set_clipboard(trimmed)
        return
    # Do not set AXSelectedText: Chrome/Safari address bars show the string
    # but do not treat it as typed, so Return does nothing until another key.
    _paste_via_clipboard(trimmed)


def _set_clipboard(text: str) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)


def _snapshot(pasteboard: NSPasteboard) -> list[dict]:
    items = []
    for item in pasteboard.pasteboardItems() or []:
        payload = {}
        for ptype in item.types() or []:
            data = item.dataForType_(ptype)
            if data is not None:
                payload[ptype] = data
        if payload:
            items.append(payload)
    return items


def _restore(pasteboard: NSPasteboard, items: list[dict]) -> None:
    pasteboard.clearContents()
    written = []
    for payload in items:
        item = NSPasteboardItem.alloc().init()
        for ptype, data in payload.items():
            item.setData_forType_(data, ptype)
        written.append(item)
    if written:
        pasteboard.writeObjects_(written)


def _paste_via_clipboard(text: str) -> None:
    pasteboard = NSPasteboard.generalPasteboard()
    snapshot = _snapshot(pasteboard)
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)
    empty = NSData.data()
    pasteboard.setData_forType_(empty, _TRANSIENT)
    pasteboard.setData_forType_(empty, _CONCEALED)
    stamp = pasteboard.changeCount()
    _post_command_v()
    time.sleep(0.08)
    _nudge_field()

    def restore_if_ours() -> None:
        if pasteboard.changeCount() == stamp:
            _restore(pasteboard, snapshot)

    Timer(0.3, restore_if_ours).start()


def press_return() -> None:
    _post_key(_VK_RETURN, flags=0)


def press_backspace(times: int = 1) -> None:
    for _ in range(max(times, 0)):
        _post_key(_VK_DELETE, flags=0)
        time.sleep(0.008)


def press_option_backspace() -> None:
    _post_key(_VK_DELETE, flags=kCGEventFlagMaskAlternate | _NONCOALESCED)


def press_undo() -> None:
    _post_key(_VK_ANSI_Z, flags=kCGEventFlagMaskCommand | _NONCOALESCED)


def _nudge_field() -> None:
    """Space then delete so the host registers a keystroke after paste."""
    _post_key(_VK_SPACE, flags=0)
    time.sleep(0.03)
    _post_key(_VK_DELETE, flags=0)


def _post_command_v() -> None:
    _post_key(_VK_ANSI_V, flags=kCGEventFlagMaskCommand | _NONCOALESCED)


def _post_key(keycode: int, flags: int) -> None:
    source = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)
    down = CGEventCreateKeyboardEvent(source, keycode, True)
    up = CGEventCreateKeyboardEvent(source, keycode, False)
    CGEventSetFlags(down, flags)
    CGEventSetFlags(up, flags)
    CGEventPost(kCGSessionEventTap, down)
    CGEventPost(kCGSessionEventTap, up)
