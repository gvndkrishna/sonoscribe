"""Installed macOS apps, frontmost identity, and command app-scope helpers."""

from __future__ import annotations

import plistlib
import threading
import time
from pathlib import Path
from typing import Any

from sonoscribe.scripts import looks_like_bundle_id

_APP_ROOTS = (
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path("/Applications/Utilities"),
    Path.home() / "Applications",
)
MAX_APPS = 12
_LIST_TTL = 60.0
_ICON_SIZE = 64

_lock = threading.Lock()
_list_cache: tuple[float, int, list[dict[str, str]]] | None = None
_icon_cache: dict[str, bytes] = {}


def read_app(path: Path) -> dict[str, str]:
    name = path.stem
    bundle_id = ""
    info = path / "Contents" / "Info.plist"
    if info.is_file():
        try:
            data = plistlib.loads(info.read_bytes())
        except Exception:
            data = {}
        if isinstance(data, dict):
            display = data.get("CFBundleDisplayName") or data.get("CFBundleName")
            if display:
                name = str(display)
            ident = data.get("CFBundleIdentifier")
            if ident:
                bundle_id = str(ident)
    return {"name": name, "bundle_id": bundle_id, "path": str(path)}


def list_installed_apps(limit: int = 400) -> list[dict[str, str]]:
    global _list_cache
    now = time.monotonic()
    with _lock:
        cached = _list_cache
        if cached is not None and cached[1] == limit and now - cached[0] < _LIST_TTL:
            return [dict(item) for item in cached[2]]
    found = _scan_installed_apps(limit)
    with _lock:
        _list_cache = (now, limit, found)
    return [dict(item) for item in found]


def _scan_installed_apps(limit: int) -> list[dict[str, str]]:
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    found: list[dict[str, str]] = []
    for root in _APP_ROOTS:
        if not root.is_dir():
            continue
        candidates = sorted(root.glob("*.app"))
        if root.name == "Applications":
            candidates.extend(sorted(root.glob("*/*.app")))
        for app_path in candidates:
            if not app_path.is_dir():
                continue
            info = read_app(app_path)
            if info["path"] in seen_paths:
                continue
            if info["bundle_id"] and info["bundle_id"] in seen_ids:
                continue
            seen_paths.add(info["path"])
            if info["bundle_id"]:
                seen_ids.add(info["bundle_id"])
            found.append(info)
            if len(found) >= limit:
                return sorted(found, key=lambda item: item["name"].lower())
    return sorted(found, key=lambda item: item["name"].lower())


def pick_result(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    bundle_id = str(raw.get("bundle_id") or "").strip()
    path = str(raw.get("path") or "").strip()
    if not name and not bundle_id and not path:
        return None
    return {"name": name, "bundle_id": bundle_id, "path": path}


def clean_apps(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in raw:
        bundle_id = ""
        name = ""
        if isinstance(item, str):
            text = item.strip()
            if looks_like_bundle_id(text):
                bundle_id = text
            else:
                name = text
        elif isinstance(item, dict):
            bundle_id = str(item.get("bundle_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if looks_like_bundle_id(name) and not looks_like_bundle_id(bundle_id):
                bundle_id = name
                name = str(item.get("label") or "").strip()
        else:
            continue
        name = name[:80]
        if not bundle_id and not name:
            continue
        key = bundle_id.lower() if bundle_id else f"name:{name.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"bundle_id": bundle_id, "name": name or _name_from_bundle_id(bundle_id)})
        if len(out) >= MAX_APPS:
            break
    return out


def app_scope_ids(item: dict[str, Any]) -> frozenset[str]:
    ids: set[str] = set()
    for app in clean_apps(item.get("apps")):
        bundle_id = str(app.get("bundle_id") or "").strip().lower()
        if bundle_id:
            ids.add(bundle_id)
            continue
        name = str(app.get("name") or "").strip().lower()
        if name:
            ids.add(f"name:{name}")
    return frozenset(ids)


def scopes_overlap(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left and not right:
        return True
    if not left or not right:
        return False
    return bool(left & right)


def item_on_apps(item: dict[str, Any], frontmost: dict[str, str] | None) -> bool:
    assigned = clean_apps(item.get("apps"))
    if not assigned:
        return True
    if not frontmost:
        return False
    return any(_app_matches(app, frontmost) for app in assigned)


def frontmost_app() -> dict[str, str] | None:
    try:
        from AppKit import NSWorkspace
    except Exception:
        return None
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None
    if app is None:
        return None
    try:
        bundle_id = str(app.bundleIdentifier() or "").strip()
        name = str(app.localizedName() or "").strip()
    except Exception:
        return None
    if not bundle_id and not name:
        return None
    return {"bundle_id": bundle_id, "name": name}


def app_icon_png(bundle_id: str, size: int = _ICON_SIZE) -> bytes | None:
    ident = str(bundle_id or "").strip()
    if not ident:
        return None
    with _lock:
        cached = _icon_cache.get(ident)
    if cached is not None:
        return cached
    png = _render_icon_png(ident, size)
    if png:
        with _lock:
            _icon_cache[ident] = png
    return png


def clear_app_cache() -> None:
    global _list_cache
    with _lock:
        _list_cache = None
        _icon_cache.clear()


def _name_from_bundle_id(bundle_id: str) -> str:
    if not bundle_id:
        return ""
    return bundle_id.rsplit(".", 1)[-1][:80]


def _app_matches(app: dict[str, str], frontmost: dict[str, str]) -> bool:
    app_id = str(app.get("bundle_id") or "").strip().lower()
    front_id = str(frontmost.get("bundle_id") or "").strip().lower()
    if app_id and front_id:
        return app_id == front_id
    app_name = str(app.get("name") or "").strip().lower()
    front_name = str(frontmost.get("name") or "").strip().lower()
    return bool(app_name and front_name and app_name == front_name)


def _render_icon_png(bundle_id: str, size: int) -> bytes | None:
    try:
        from AppKit import NSBitmapImageRep, NSGraphicsContext, NSWorkspace
    except Exception:
        return None
    try:
        from AppKit import NSBitmapImageRepFileTypePNG as png_type
    except Exception:
        try:
            from AppKit import NSPNGFileType as png_type
        except Exception:
            png_type = 4
    path = _path_for_bundle_id(bundle_id)
    if not path:
        return None
    try:
        icon = NSWorkspace.sharedWorkspace().iconForFile_(path)
        if icon is None:
            return None
        width = max(16, int(size))
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None,
            width,
            width,
            8,
            4,
            True,
            False,
            "NSDeviceRGBColorSpace",
            0,
            0,
        )
        if rep is None:
            return None
        context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        if context is None:
            return None
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.setCurrentContext_(context)
        icon.drawInRect_fromRect_operation_fraction_(
            ((0.0, 0.0), (float(width), float(width))),
            ((0.0, 0.0), (0.0, 0.0)),
            2,
            1.0,
        )
        NSGraphicsContext.restoreGraphicsState()
        data = rep.representationUsingType_properties_(png_type, None)
        if data is None:
            return None
        return bytes(data)
    except Exception:
        return None


def _path_for_bundle_id(bundle_id: str) -> str:
    try:
        from AppKit import NSWorkspace
    except Exception:
        NSWorkspace = None  # type: ignore[assignment]
    if NSWorkspace is not None:
        try:
            url = NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(bundle_id)
            if url is not None:
                path = str(url.path() or "").strip()
                if path:
                    return path
        except Exception:
            pass
    for item in list_installed_apps():
        if item.get("bundle_id") == bundle_id and item.get("path"):
            return str(item["path"])
    return ""
