"""Recorded keystrokes: virtual keycodes and modifier flags."""

from __future__ import annotations

from typing import Any

ALLOWED_MODS = ("command", "shift", "option", "control")
_MOD_SET = set(ALLOWED_MODS)
_VK_ESCAPE = 0x35
MODIFIER_VKS = frozenset(
    {
        0x36,  # right command
        0x37,  # left command
        0x38,  # left shift
        0x39,  # caps lock
        0x3A,  # left option
        0x3B,  # left control
        0x3C,  # right shift
        0x3D,  # right option
        0x3E,  # right control
        0x3F,  # fn
    }
)
_VK_LABELS = {
    0x00: "A",
    0x01: "S",
    0x02: "D",
    0x03: "F",
    0x04: "H",
    0x05: "G",
    0x06: "Z",
    0x07: "X",
    0x08: "C",
    0x09: "V",
    0x0B: "B",
    0x0C: "Q",
    0x0D: "W",
    0x0E: "E",
    0x0F: "R",
    0x10: "Y",
    0x11: "T",
    0x12: "1",
    0x13: "2",
    0x14: "3",
    0x15: "4",
    0x16: "6",
    0x17: "5",
    0x18: "=",
    0x19: "9",
    0x1A: "7",
    0x1B: "-",
    0x1C: "8",
    0x1D: "0",
    0x1E: "]",
    0x1F: "O",
    0x20: "U",
    0x21: "[",
    0x22: "I",
    0x23: "P",
    0x24: "Enter",
    0x25: "L",
    0x26: "J",
    0x27: "'",
    0x28: "K",
    0x29: ";",
    0x2A: "\\",
    0x2B: ",",
    0x2C: "/",
    0x2D: "N",
    0x2E: "M",
    0x2F: ".",
    0x30: "Tab",
    0x31: "Space",
    0x32: "`",
    0x33: "Backspace",
    0x35: "Escape",
    0x7A: "F1",
    0x78: "F2",
    0x63: "F3",
    0x76: "F4",
    0x60: "F5",
    0x61: "F6",
    0x62: "F7",
    0x64: "F8",
    0x65: "F9",
    0x6D: "F10",
    0x67: "F11",
    0x6F: "F12",
    0x7B: "Left",
    0x7C: "Right",
    0x7D: "Down",
    0x7E: "Up",
}

_MOD_MARKS = (("control", "⌃"), ("option", "⌥"), ("shift", "⇧"), ("command", "⌘"))


def clean_keys(raw: Any, prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [f"{prefix}: keys must be a list"]
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, step in enumerate(raw):
        label = f"{prefix} key {index + 1}"
        if not isinstance(step, dict):
            errors.append(f"{label} must be an object")
            continue
        try:
            vk = int(step.get("vk"))
        except (TypeError, ValueError):
            errors.append(f"{label}: vk is required")
            continue
        if vk < 0 or vk > 0x7F:
            errors.append(f"{label}: vk is out of range")
            continue
        mods = [str(item) for item in (step.get("mods") or []) if str(item) in _MOD_SET]
        text = str(step.get("label") or "").strip()[:40]
        out.append({"vk": vk, "mods": mods, "label": text})
    return out, errors


def format_keys(keys: list[dict[str, Any]]) -> str:
    return " ".join(str(step.get("label") or "") for step in keys if step.get("label")).strip()


def chord_label(vk: int, mods: list[str]) -> str:
    bits = [mark for name, mark in _MOD_MARKS if name in mods]
    bits.append(_VK_LABELS.get(int(vk), f"0x{int(vk):02x}"))
    return "".join(bits)


def capture_step(vk: int, command: bool, shift: bool, option: bool, control: bool) -> str | dict[str, Any] | None:
    """Classify a key-down for shortcut recording.

    Returns 'stop' for Escape, None for modifiers, or a recorded step.
    """
    if vk in MODIFIER_VKS:
        return None
    mods = [name for name, flag in (("control", control), ("option", option), ("shift", shift), ("command", command)) if flag]
    if vk == _VK_ESCAPE and not mods:
        return "stop"
    return {"vk": int(vk), "mods": mods, "label": chord_label(vk, mods)}
