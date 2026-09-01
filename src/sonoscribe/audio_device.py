"""Mute and volume via Core Audio (AppleScript volume is a no-op on modern macOS)."""

from __future__ import annotations

import json
import os
from ctypes import (
    Structure,
    byref,
    c_char_p,
    c_float,
    c_int32,
    c_uint32,
    c_void_p,
    cdll,
    create_string_buffer,
    sizeof,
)
from ctypes.util import find_library
from pathlib import Path


def _fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


_kAudioObjectSystemObject = 1
_kAudioHardwarePropertyDefaultOutputDevice = _fourcc("dOut")
_kAudioHardwarePropertyDevices = _fourcc("dev#")
_kAudioDevicePropertyMute = _fourcc("mute")
_kAudioDevicePropertyVolumeScalar = _fourcc("volm")
_kAudioHardwareServiceVirtualMasterVolume = _fourcc("vmvc")
_kAudioDevicePropertyTransportType = _fourcc("tran")
_kAudioObjectPropertyName = _fourcc("lnam")
_kAudioObjectPropertyScopeGlobal = _fourcc("glob")
_kAudioObjectPropertyScopeOutput = _fourcc("outp")
_kAudioObjectPropertyElementMain = 0
_NO_ERROR = 0
_ENV_AUDIO_STATE = "SONOSCRIBE_AUDIO_STATE"


class _Address(Structure):
    _fields_ = [
        ("mSelector", c_uint32),
        ("mScope", c_uint32),
        ("mElement", c_uint32),
    ]


def _core():
    lib = find_library("CoreAudio")
    if not lib:
        raise RuntimeError("CoreAudio is not available.")
    core = cdll.LoadLibrary(lib)
    core.AudioObjectGetPropertyData.argtypes = [
        c_uint32,
        c_void_p,
        c_uint32,
        c_void_p,
        c_void_p,
        c_void_p,
    ]
    core.AudioObjectGetPropertyData.restype = c_int32
    core.AudioObjectSetPropertyData.argtypes = [
        c_uint32,
        c_void_p,
        c_uint32,
        c_void_p,
        c_uint32,
        c_void_p,
    ]
    core.AudioObjectSetPropertyData.restype = c_int32
    core.AudioObjectGetPropertyDataSize.argtypes = [
        c_uint32,
        c_void_p,
        c_uint32,
        c_void_p,
        c_void_p,
    ]
    core.AudioObjectGetPropertyDataSize.restype = c_int32
    return core


def _state_path() -> Path:
    override = os.environ.get(_ENV_AUDIO_STATE)
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Sonoscribe" / "audio-state.json"


def _default_output_device(core) -> int:
    addr = _Address(
        _kAudioHardwarePropertyDefaultOutputDevice,
        _kAudioObjectPropertyScopeGlobal,
        _kAudioObjectPropertyElementMain,
    )
    device = c_uint32(0)
    size = c_uint32(sizeof(device))
    status = core.AudioObjectGetPropertyData(
        _kAudioObjectSystemObject, byref(addr), 0, None, byref(size), byref(device)
    )
    if status != _NO_ERROR or not device.value:
        raise RuntimeError(f"Could not read the default output device ({status}).")
    return int(device.value)


def _all_devices(core) -> list[int]:
    addr = _Address(
        _kAudioHardwarePropertyDevices,
        _kAudioObjectPropertyScopeGlobal,
        _kAudioObjectPropertyElementMain,
    )
    size = c_uint32(0)
    status = core.AudioObjectGetPropertyDataSize(
        _kAudioObjectSystemObject, byref(addr), 0, None, byref(size)
    )
    if status != _NO_ERROR or size.value < sizeof(c_uint32):
        return [_default_output_device(core)]
    count = size.value // sizeof(c_uint32)
    devices = (c_uint32 * count)()
    status = core.AudioObjectGetPropertyData(
        _kAudioObjectSystemObject, byref(addr), 0, None, byref(size), devices
    )
    if status != _NO_ERROR:
        return [_default_output_device(core)]
    return [int(item) for item in devices]


def _transport(core, device: int) -> str:
    status, value = _get(
        core,
        device,
        _kAudioDevicePropertyTransportType,
        _kAudioObjectPropertyElementMain,
        c_uint32,
        scope=_kAudioObjectPropertyScopeGlobal,
    )
    if status != _NO_ERROR:
        return ""
    try:
        return int(value.value).to_bytes(4, "big").decode("ascii", "replace")
    except Exception:
        return ""


def _device_name(core, device: int) -> str:
    cf = cdll.LoadLibrary(find_library("CoreFoundation"))
    cf.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_int32, c_uint32]
    cf.CFStringGetCString.restype = c_uint32
    cf.CFRelease.argtypes = [c_void_p]
    addr = _Address(
        _kAudioObjectPropertyName,
        _kAudioObjectPropertyScopeGlobal,
        _kAudioObjectPropertyElementMain,
    )
    ptr = c_void_p()
    size = c_uint32(sizeof(ptr))
    status = core.AudioObjectGetPropertyData(
        device, byref(addr), 0, None, byref(size), byref(ptr)
    )
    if status != _NO_ERROR or not ptr.value:
        return f"device {device}"
    buf = create_string_buffer(256)
    cf.CFStringGetCString(ptr, buf, 256, 0x08000100)
    cf.CFRelease(ptr)
    return buf.value.decode("utf-8", "replace") or f"device {device}"


def has_bluetooth_output() -> bool:
    core = _core()
    for device in _all_devices(core):
        transport = _transport(core, device)
        if transport.startswith("bt") or transport == "blue":
            if _read_volume(core, device) is not None:
                return True
    return False


def _get(core, device: int, selector: int, element: int, ctype, scope: int | None = None):
    addr = _Address(
        selector,
        _kAudioObjectPropertyScopeOutput if scope is None else scope,
        element,
    )
    value = ctype()
    size = c_uint32(sizeof(value))
    status = core.AudioObjectGetPropertyData(
        device, byref(addr), 0, None, byref(size), byref(value)
    )
    return status, value


def _set(core, device: int, selector: int, element: int, value) -> int:
    addr = _Address(selector, _kAudioObjectPropertyScopeOutput, element)
    size = c_uint32(sizeof(value))
    return int(
        core.AudioObjectSetPropertyData(device, byref(addr), 0, None, size, byref(value))
    )


def _elements_supporting(core, device: int, selector: int, ctype) -> list[int]:
    found: list[int] = []
    for element in range(0, 8):
        status, _value = _get(core, device, selector, element, ctype)
        if status == _NO_ERROR:
            found.append(element)
    return found


def _read_volume(core, device: int) -> float | None:
    values: list[float] = []
    for element in _elements_supporting(
        core, device, _kAudioDevicePropertyVolumeScalar, c_float
    ):
        status, current = _get(
            core, device, _kAudioDevicePropertyVolumeScalar, element, c_float
        )
        if status == _NO_ERROR:
            values.append(float(current.value))
    if not values:
        return None
    return max(values)


def _write_volume(core, device: int, scalar: float) -> bool:
    value = c_float(max(0.0, min(1.0, scalar)))
    ok = False
    for element in _elements_supporting(
        core, device, _kAudioDevicePropertyVolumeScalar, c_float
    ):
        if _set(core, device, _kAudioDevicePropertyVolumeScalar, element, value) == _NO_ERROR:
            ok = True
    master = _elements_supporting(
        core, device, _kAudioHardwareServiceVirtualMasterVolume, c_float
    )
    for element in master or [_kAudioObjectPropertyElementMain]:
        if (
            _set(core, device, _kAudioHardwareServiceVirtualMasterVolume, element, value)
            == _NO_ERROR
        ):
            ok = True
    return ok


def _write_mute_flags(core, muted: bool) -> None:
    flag = c_uint32(1 if muted else 0)
    for device in _all_devices(core):
        for element in _elements_supporting(
            core, device, _kAudioDevicePropertyMute, c_uint32
        ):
            _set(core, device, _kAudioDevicePropertyMute, element, flag)


def _load_saved_volumes() -> dict[str, float]:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data.get("devices"), dict):
        out: dict[str, float] = {}
        for key, raw in data["devices"].items():
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                out[str(key)] = max(0.05, min(1.0, value))
        return out
    try:
        value = float(data.get("volume"))
    except (TypeError, ValueError):
        return {}
    if value <= 0:
        return {}
    return {"default": max(0.05, min(1.0, value))}


def _save_volumes(devices: dict[str, float]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"devices": devices}) + "\n", encoding="utf-8")


def set_output_muted(muted: bool) -> None:
    """Silence every output that exposes volume. Mute flags alone do not stop playback."""
    core = _core()
    devices = _all_devices(core)
    if muted:
        saved: dict[str, float] = {}
        silenced = 0
        for device in devices:
            current = _read_volume(core, device)
            if current is not None and current > 0.01:
                saved[str(device)] = current
            if current is not None and _write_volume(core, device, 0.0):
                silenced += 1
        if saved:
            _save_volumes(saved)
        _write_mute_flags(core, True)
        try:
            names = ", ".join(
                _device_name(core, device)
                for device in devices
                if str(device) in saved or _read_volume(core, device) is not None
            )
        except Exception:
            names = ""
        print(f"Audio: muted {silenced} output(s){f' ({names})' if names else ''}", flush=True)
        return
    saved = _load_saved_volumes()
    _write_mute_flags(core, False)
    restored = 0
    for device in devices:
        scalar = saved.get(str(device))
        if scalar is None and len(saved) == 1 and "default" in saved:
            scalar = saved["default"]
        if scalar is None:
            continue
        if _write_volume(core, device, scalar):
            restored += 1
    print(f"Audio: restored {restored} output device(s)", flush=True)


def adjust_output_volume(delta: float) -> None:
    """Change default-output volume. `delta` is a scalar step, about 0.12 per notch."""
    core = _core()
    device = _default_output_device(core)
    current = _read_volume(core, device)
    if current is None:
        raise RuntimeError("This output device does not expose volume.")
    nxt = max(0.0, min(1.0, current + delta))
    if not _write_volume(core, device, nxt):
        raise RuntimeError("Could not set output volume.")
    if nxt > 0.01:
        _save_volumes({str(device): nxt})
        _write_mute_flags(core, False)
