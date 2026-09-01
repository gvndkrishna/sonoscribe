"""TCC helpers for microphone and Accessibility."""

from __future__ import annotations

import subprocess
import sys

from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
from Foundation import kCFBooleanTrue

from sonoscribe.runtime import frozen, in_app_bundle


def is_frozen() -> bool:
    return frozen()


def process_label() -> str:
    if in_app_bundle():
        return "Sonoscribe.app"
    if is_frozen():
        return sys.executable
    return "Terminal (or iTerm / VS Code — the app hosting this Python process)"


def accessibility_granted() -> bool:
    return bool(AXIsProcessTrusted())


def prompt_accessibility() -> None:
    AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: kCFBooleanTrue})


def open_accessibility_settings() -> None:
    _open_pref(
        [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility",
        ]
    )


def open_microphone_settings() -> None:
    _open_pref(
        [
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Microphone",
        ]
    )


def _open_pref(urls: list[str]) -> None:
    for url in urls:
        result = subprocess.run(["open", url], check=False)
        if result.returncode == 0:
            return


def permission_help() -> str:
    target = process_label()
    return (
        "Sonoscribe needs Microphone and Accessibility.\n"
        f"  Add this target: {target}\n"
        "  System Settings → Privacy & Security → Microphone\n"
        "  System Settings → Privacy & Security → Accessibility\n"
        "If you granted access while running via `uv run`, the permission is on "
        "Terminal (or your IDE), not on Sonoscribe.app — grant the app separately."
    )
