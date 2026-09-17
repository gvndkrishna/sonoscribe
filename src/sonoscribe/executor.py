"""Run a matched command: keyboard, website, app, file, or system."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    CGEventSourceCreate,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskShift,
    kCGEventSourceStateCombinedSessionState,
    kCGHIDEventTap,
    kCGSessionEventTap,
)
from AppKit import NSEvent

from sonoscribe.actions import (
    BACKSPACE,
    DELETE_SENTENCE,
    DELETE_WORD,
    ENTER,
    SCRATCH,
    action_label,
    last_sentence_chars,
    trim_last_word,
)
from sonoscribe.audio_device import (
    adjust_output_volume,
    has_bluetooth_output,
    set_output_muted,
)
from sonoscribe.inserter import (
    insert,
    press_backspace,
    press_option_backspace,
    press_return,
    press_undo,
)
from sonoscribe.keys import format_keys
from sonoscribe.scripts import ScriptError, looks_like_bundle_id, run_script
from sonoscribe.slots import fill

_VK_ANSI_Q = 0x0C
_VK_ANSI_3 = 0x14
_VK_ANSI_4 = 0x15
_NONCOALESCED = 0x000008

# NX system-defined media keys.
_NX_SOUND_UP = 0
_NX_SOUND_DOWN = 1
_NX_PLAY = 16
_NX_NEXT = 17
_NX_PREVIOUS = 18
_NS_SYSTEM_DEFINED = 14
_BT_VOLUME_STEPS = 20
_MOD_FLAGS = {
    "command": kCGEventFlagMaskCommand,
    "shift": kCGEventFlagMaskShift,
    "option": kCGEventFlagMaskAlternate,
    "control": kCGEventFlagMaskControl,
}


class KeyboardState:
    def __init__(self) -> None:
        self.last_inserted = ""


def run_command(
    command: dict[str, Any],
    keyboard: KeyboardState,
    bindings: dict[str, str] | None = None,
    variables: dict[str, str] | None = None,
) -> str:
    bound = bindings or {}
    names = variables or {}
    cmd_type = command.get("type")
    if cmd_type == "keyboard":
        keys = command.get("keys") or []
        if keys:
            _play_keys(keys)
            return command.get("name") or format_keys(keys) or "Keyboard"
        return _run_keyboard(str(command.get("action") or ""), keyboard)
    if cmd_type == "website":
        url = fill(str(command.get("url") or ""), bound, names)
        _open([url])
        return command.get("name") or "Website"
    if cmd_type == "app":
        bundle_id = fill(str(command.get("bundle_id") or "").strip(), bound, names)
        app = fill(str(command.get("app") or "").strip(), bound, names)
        target = bundle_id or app
        if looks_like_bundle_id(target):
            _open(["-b", target])
        elif target:
            _open(["-a", target])
        return command.get("name") or target
    if cmd_type == "file":
        path = fill(str(command.get("path") or ""), bound, names)
        _open([path])
        return command.get("name") or path
    if cmd_type == "system":
        return _run_system(str(command.get("action") or ""))
    if cmd_type == "script":
        try:
            run_script(
                str(command.get("runtime") or "bash"),
                body=fill(str(command.get("body") or ""), bound, names),
                path=fill(str(command.get("path") or ""), bound, names),
            )
        except ScriptError as exc:
            raise ValueError(str(exc)) from exc
        return command.get("name") or "Script"
    if cmd_type == "text":
        template = str(command.get("text") or "").strip() or "{*}"
        text = fill(template, bound, names)
        insert(text)
        if text.strip():
            keyboard.last_inserted = text
        return command.get("name") or text or "Text"
    raise ValueError(f"Unknown command type {cmd_type!r}")


def run_routine_steps(
    routine: dict[str, Any],
    lookup: Callable[[str], dict[str, Any] | None],
    keyboard: KeyboardState,
    log: Callable[[str], None],
    on_command: Callable[[dict[str, Any], str], None] | None = None,
    invoke: Callable[[dict[str, Any], KeyboardState], str] | None = None,
    bindings: dict[str, str] | None = None,
    variables: dict[str, str] | None = None,
) -> None:
    bound = bindings or {}
    names = variables or {}

    def default_runner(command: dict[str, Any], state: KeyboardState) -> str:
        return run_command(command, state, bindings=bound, variables=names)

    runner = invoke or default_runner
    steps = routine.get("steps") or []
    for step in steps:
        delay_ms = int(step.get("delay_ms") or 0)
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        command_id = str(step.get("command_id") or "")
        command = lookup(command_id)
        if command is None:
            log(f"Skipped missing command {command_id}")
            continue
        label = runner(command, keyboard)
        if on_command:
            on_command(command, label)
        log(label)


def _run_keyboard(action: str, keyboard: KeyboardState) -> str:
    if action == ENTER:
        press_return()
    elif action == BACKSPACE:
        press_backspace(1)
        if keyboard.last_inserted:
            keyboard.last_inserted = keyboard.last_inserted[:-1]
    elif action == DELETE_WORD:
        press_option_backspace()
        keyboard.last_inserted = trim_last_word(keyboard.last_inserted)
    elif action == DELETE_SENTENCE:
        n = last_sentence_chars(keyboard.last_inserted)
        if n:
            press_backspace(n)
            keyboard.last_inserted = keyboard.last_inserted[: len(keyboard.last_inserted) - n]
        else:
            press_option_backspace()
    elif action == SCRATCH:
        press_undo()
        keyboard.last_inserted = ""
    else:
        raise ValueError(f"Unknown keyboard action {action!r}")
    return action_label(action)


def _open(args: list[str]) -> None:
    subprocess.run(["open", *args], check=False)


def _run_system(action: str) -> str:
    labels = {
        "mute": "Mute",
        "unmute": "Unmute",
        "volume_up": "Volume up",
        "volume_down": "Volume down",
        "play_pause": "Play/pause",
        "next": "Next track",
        "previous": "Previous track",
        "lock": "Lock screen",
        "sleep": "Sleep",
        "display_sleep": "Sleep display",
        "screenshot": "Screenshot",
        "screenshot_selection": "Screenshot selection",
    }
    if action == "mute":
        set_output_muted(True)
        # Sony and other BT headsets ignore HAL volume; they follow
        # keyboard volume keys over AVRCP. Do not send NX_MUTE — it
        # toggles and remutes MacBook speakers when they are default.
        if has_bluetooth_output():
            for _ in range(_BT_VOLUME_STEPS):
                _media_key(_NX_SOUND_DOWN)
                time.sleep(0.02)
    elif action == "unmute":
        # Restore built-in speaker HAL volume first. Media keys hit the
        # default output only; spraying them first can leave speakers at
        # one leftover notch, then overwrite the saved level with that.
        set_output_muted(False)
        if has_bluetooth_output():
            for _ in range(_BT_VOLUME_STEPS):
                _media_key(_NX_SOUND_UP)
                time.sleep(0.02)
    elif action == "volume_up":
        adjust_output_volume(0.12)
    elif action == "volume_down":
        adjust_output_volume(-0.12)
    elif action == "play_pause":
        _media_key(_NX_PLAY)
    elif action == "next":
        _media_key(_NX_NEXT)
    elif action == "previous":
        _media_key(_NX_PREVIOUS)
    elif action == "lock":
        _post_key(_VK_ANSI_Q, kCGEventFlagMaskControl | kCGEventFlagMaskCommand | _NONCOALESCED)
    elif action == "sleep":
        subprocess.run(["pmset", "sleepnow"], check=False)
    elif action == "display_sleep":
        subprocess.run(["pmset", "displaysleepnow"], check=False)
    elif action == "screenshot":
        _post_key(
            _VK_ANSI_3,
            kCGEventFlagMaskCommand | kCGEventFlagMaskShift | _NONCOALESCED,
        )
    elif action == "screenshot_selection":
        _post_key(
            _VK_ANSI_4,
            kCGEventFlagMaskCommand | kCGEventFlagMaskShift | _NONCOALESCED,
        )
    else:
        raise ValueError(f"Unknown system action {action!r}")
    return labels.get(action, action)


def _play_keys(steps: list[dict[str, Any]]) -> None:
    for step in steps:
        flags = _NONCOALESCED
        for mod in step.get("mods") or []:
            flags |= _MOD_FLAGS.get(str(mod), 0)
        _post_key(int(step["vk"]), flags)
        time.sleep(0.02)


def _post_key(keycode: int, flags: int) -> None:
    source = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)
    down = CGEventCreateKeyboardEvent(source, keycode, True)
    up = CGEventCreateKeyboardEvent(source, keycode, False)
    CGEventSetFlags(down, flags)
    CGEventSetFlags(up, flags)
    CGEventPost(kCGSessionEventTap, down)
    CGEventPost(kCGSessionEventTap, up)


def _media_key(key_type: int) -> None:
    for down in (True, False):
        flags = 0xA00 if down else 0xB00
        data1 = (key_type << 16) | ((0xA if down else 0xB) << 8)
        event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            _NS_SYSTEM_DEFINED,
            (0.0, 0.0),
            flags,
            0.0,
            0,
            None,
            8,
            data1,
            -1,
        )
        if event is not None:
            CGEventPost(kCGHIDEventTap, event.CGEvent())
