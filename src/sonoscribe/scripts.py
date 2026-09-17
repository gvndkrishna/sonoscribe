"""User-level AppleScript and bash. No elevation."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

RUNTIMES = ("bash", "applescript")
_MAX_BODY = 64_000
_TIMEOUT = 30

_ELEVATED = (
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bdoas\b", re.IGNORECASE),
    re.compile(r"\bpkexec\b", re.IGNORECASE),
    re.compile(r"(^|[\s;&|])su\s", re.IGNORECASE),
    re.compile(r"with administrator privileges", re.IGNORECASE),
    re.compile(r"AuthorizationExecuteWithPrivileges", re.IGNORECASE),
    re.compile(r"osascript\s+.*-e\s+.*administrator", re.IGNORECASE),
)


class ScriptError(ValueError):
    pass


def looks_like_bundle_id(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+", value.strip()))


def runtime_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".applescript", ".scpt", ".as"}:
        return "applescript"
    return "bash"


def assert_user_level(source: str) -> None:
    for pattern in _ELEVATED:
        if pattern.search(source):
            raise ScriptError("Elevated or administrator scripts are not allowed.")


def run_script(runtime: str, body: str = "", path: str = "") -> str:
    kind = runtime if runtime in RUNTIMES else ""
    if not kind:
        raise ScriptError("Script runtime must be bash or applescript.")
    text = body.strip()
    file_path = Path(path).expanduser() if path.strip() else None
    if file_path is not None:
        if not file_path.is_file():
            raise ScriptError("Script file was not found.")
        if file_path.suffix.lower() != ".scpt":
            try:
                text = file_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ScriptError(f"Could not read script: {exc}") from exc
            assert_user_level(text)
        _exec(kind, file_path)
        return "Script"
    if not text:
        raise ScriptError("Paste a script or choose a file.")
    if len(text) > _MAX_BODY:
        raise ScriptError("Script is too long.")
    assert_user_level(text)
    suffix = ".applescript" if kind == "applescript" else ".sh"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=True) as handle:
        handle.write(text)
        handle.flush()
        _exec(kind, Path(handle.name))
    return "Script"


def _exec(runtime: str, path: Path) -> None:
    if runtime == "applescript":
        cmd = ["/usr/bin/osascript", str(path)]
    else:
        cmd = ["/bin/bash", str(path)]
    try:
        subprocess.run(
            cmd,
            check=False,
            timeout=_TIMEOUT,
            cwd=str(Path.home()),
            capture_output=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScriptError("Script timed out.") from exc
