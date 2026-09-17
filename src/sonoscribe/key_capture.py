"""Swallow browser-reserved shortcuts while the dashboard records a chord."""

from __future__ import annotations

import threading
import time
from typing import Any

from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGHeadInsertEventTap,
    kCGHIDEventTap,
    kCGKeyboardEventKeycode,
)

from sonoscribe.keys import MODIFIER_VKS, capture_step

try:
    from Quartz import kCGEventTapOptionDefault as _TAP_DEFAULT
except ImportError:  # pragma: no cover
    _TAP_DEFAULT = 0

try:
    from Quartz import kCGKeyboardEventAutorepeat as _AUTOREPEAT
except ImportError:  # pragma: no cover
    _AUTOREPEAT = 8

_MAX_SECONDS = 25.0


class KeyCapture:
    """Active HID tap. While on, key-downs never reach Edge/Chrome."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: list[dict[str, Any]] = []
        self._stop_requested = False
        self._active = False
        self._started_at = 0.0
        self._tap = None
        self._source = None
        self._callback = self._handle

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._active:
                self._pending = []
                self._stop_requested = False
                self._started_at = time.monotonic()
                return {"ok": True, "native": True}
            mask = (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)
            tap = CGEventTapCreate(
                kCGHIDEventTap,
                kCGHeadInsertEventTap,
                _TAP_DEFAULT,
                mask,
                self._callback,
                None,
            )
            if tap is None:
                return {"ok": False, "native": False}
            source = CFMachPortCreateRunLoopSource(None, tap, 0)
            CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
            CGEventTapEnable(tap, True)
            self._tap = tap
            self._source = source
            self._pending = []
            self._stop_requested = False
            self._started_at = time.monotonic()
            self._active = True
            return {"ok": True, "native": True}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._disable_locked()
            pending = self._pending
            stopped = self._stop_requested
            self._pending = []
            self._stop_requested = False
        return {"ok": True, "native": False, "keys": pending, "stopped": stopped}

    def drain(self) -> dict[str, Any]:
        with self._lock:
            if self._active and self._started_at and time.monotonic() - self._started_at > _MAX_SECONDS:
                self._disable_locked()
                self._stop_requested = True
            keys = self._pending
            self._pending = []
            stopped = self._stop_requested
            native = self._active
            if stopped:
                self._stop_requested = False
        return {"keys": keys, "stopped": stopped, "native": native}

    def _disable_locked(self) -> None:
        if self._tap is not None:
            CGEventTapEnable(self._tap, False)
            self._tap = None
        self._source = None
        self._active = False

    def _handle(self, proxy: Any, event_type: int, event: Any, refcon: Any) -> Any:  # noqa: ARG002
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                CGEventTapEnable(self._tap, True)
            return event
        with self._lock:
            active = self._active
            expired = bool(self._started_at and time.monotonic() - self._started_at > _MAX_SECONDS)
        if not active:
            return event
        if expired:
            with self._lock:
                self._disable_locked()
                self._stop_requested = True
            return None
        if event_type == kCGEventKeyUp:
            keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
            return event if keycode in MODIFIER_VKS else None
        if event_type != kCGEventKeyDown:
            return event
        try:
            if int(CGEventGetIntegerValueField(event, _AUTOREPEAT)):
                return None
        except Exception:
            pass
        keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
        flags = int(CGEventGetFlags(event))
        step = capture_step(
            keycode,
            command=bool(flags & kCGEventFlagMaskCommand),
            shift=bool(flags & kCGEventFlagMaskShift),
            option=bool(flags & kCGEventFlagMaskAlternate),
            control=bool(flags & kCGEventFlagMaskControl),
        )
        if step is None:
            return event
        with self._lock:
            if step == "stop":
                self._stop_requested = True
                self._disable_locked()
            elif isinstance(step, dict):
                self._pending.append(step)
        return None
