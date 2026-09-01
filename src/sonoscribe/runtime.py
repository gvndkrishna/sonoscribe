"""Frozen vs source vs .app-bundle detection."""

from __future__ import annotations

import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def in_app_bundle() -> bool:
    """True when this process is the executable inside a .app/Contents/MacOS tree."""
    try:
        exe = Path(sys.executable).resolve()
    except OSError:
        return False
    return any(part.suffix == ".app" and (part / "Contents").is_dir() for part in exe.parents)


def default_log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "Sonoscribe" / "sonoscribe.log"


def attach_log_if_needed() -> Path | None:
    """When Finder launches the .app, stdout is not a TTY — append to a log file."""
    if not in_app_bundle() or sys.stdout.isatty():
        return None
    path = default_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = handle
    sys.stderr = handle
    return path
