"""Listen-only Fn / Globe hold via a Quartz event tap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    kCGEventFlagMaskSecondaryFn,
    kCGEventFlagMaskShift,
    kCGEventFlagsChanged,
    kCGEventKeyDown,
    kCGEventTapDisabledByTimeout,
    kCGEventTapDisabledByUserInput,
    kCGEventTapOptionListenOnly,
    kCGHeadInsertEventTap,
    kCGHIDEventTap,
    kCGKeyboardEventKeycode,
)

_VK_FUNCTION = 0x3F
_VK_COMMAND_L = 0x37
_VK_COMMAND_R = 0x36
_COMMAND_KEYS = {_VK_COMMAND_L, _VK_COMMAND_R}
_CANCEL_MODIFIERS = (
    kCGEventFlagMaskShift | kCGEventFlagMaskAlternate | kCGEventFlagMaskControl
)


@dataclass(frozen=True)
class TapState:
    fn_down: bool = False
    cmd_down: bool = False
    cancelled: bool = False


@dataclass(frozen=True)
class TapEvents:
    begin: bool = False
    end: bool = False
    cancel: bool = False
    command_begin: bool = False
    command_end: bool = False


class FnMonitorError(RuntimeError):
    pass


def apply_flags(
    state: TapState,
    fn_held: bool,
    cmd_held: bool,
    cancel_mod: bool,
) -> tuple[TapState, TapEvents]:
    """Pure Fn/Cmd/cancel transitions. Command is command-mode, not cancel."""
    if fn_held and not state.fn_down:
        if cancel_mod:
            return state, TapEvents()
        if cmd_held:
            return (
                TapState(fn_down=True, cmd_down=True, cancelled=False),
                TapEvents(begin=True, command_begin=True),
            )
        return TapState(fn_down=True), TapEvents(begin=True)

    if not state.fn_down:
        return state, TapEvents()

    if not fn_held:
        if state.cancelled:
            return TapState(), TapEvents()
        return TapState(), TapEvents(end=True, command_end=state.cmd_down)

    if state.cancelled:
        return state, TapEvents()

    if cancel_mod:
        return (
            TapState(fn_down=True, cmd_down=state.cmd_down, cancelled=True),
            TapEvents(cancel=True),
        )

    if cmd_held and not state.cmd_down:
        return (
            TapState(fn_down=True, cmd_down=True),
            TapEvents(command_begin=True),
        )
    if not cmd_held and state.cmd_down:
        return TapState(fn_down=True, cmd_down=False), TapEvents(command_end=True)
    return state, TapEvents()


def apply_keydown(state: TapState, keycode: int) -> tuple[TapState, TapEvents]:
    if not state.fn_down or state.cancelled:
        return state, TapEvents()
    if keycode == _VK_FUNCTION or keycode in _COMMAND_KEYS:
        return state, TapEvents()
    return (
        TapState(fn_down=True, cmd_down=state.cmd_down, cancelled=True),
        TapEvents(cancel=True),
    )


class FnMonitor:
    """Edge-detects Fn hold and Cmd command-mode. Listen-only (does not swallow keys)."""

    def __init__(
        self,
        on_begin: Callable[[], None],
        on_end: Callable[[], None],
        on_cancel: Callable[[], None],
        on_command_begin: Callable[[], None],
        on_command_end: Callable[[], None],
    ) -> None:
        self._on_begin = on_begin
        self._on_end = on_end
        self._on_cancel = on_cancel
        self._on_command_begin = on_command_begin
        self._on_command_end = on_command_end
        self._state = TapState()
        self._tap = None
        self._source = None
        self._callback = self._handle  # keep a strong ref for the C tap

    def start(self) -> None:
        mask = (1 << kCGEventFlagsChanged) | (1 << kCGEventKeyDown)
        tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if tap is None:
            raise FnMonitorError(
                "Could not create an event tap. Grant Accessibility to "
                "this process, then restart Sonoscribe."
            )
        source = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        self._tap = tap
        self._source = source

    def stop(self) -> None:
        if self._tap is not None:
            CGEventTapEnable(self._tap, False)
            self._tap = None
        self._source = None

    def _emit(self, events: TapEvents) -> None:
        if events.begin:
            self._on_begin()
        if events.command_begin:
            self._on_command_begin()
        if events.cancel:
            self._on_cancel()
        if events.command_end:
            self._on_command_end()
        if events.end:
            self._on_end()

    def _handle(self, proxy: Any, event_type: int, event: Any, refcon: Any) -> Any:  # noqa: ARG002
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                CGEventTapEnable(self._tap, True)
            return event

        if event_type == kCGEventKeyDown:
            keycode = int(CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode))
            self._state, events = apply_keydown(self._state, keycode)
            self._emit(events)
            return event

        if event_type != kCGEventFlagsChanged:
            return event

        flags = int(CGEventGetFlags(event))
        fn_held = bool(flags & kCGEventFlagMaskSecondaryFn)
        cmd_held = bool(flags & kCGEventFlagMaskCommand)
        cancel_mod = bool(flags & _CANCEL_MODIFIERS)
        self._state, events = apply_flags(self._state, fn_held, cmd_held, cancel_mod)
        self._emit(events)
        return event
