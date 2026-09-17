from sonoscribe import audio_device


def _stub_devices(monkeypatch, volumes: dict[int, float], written: list[tuple[int, float]], transports: dict[int, str] | None = None) -> None:
    transports = transports or {}
    monkeypatch.setattr(audio_device, "_core", lambda: "core")
    monkeypatch.setattr(audio_device, "_all_devices", lambda _core: list(volumes))
    monkeypatch.setattr(audio_device, "_read_volume", lambda _core, dev: volumes[dev])
    monkeypatch.setattr(audio_device, "_write_mute_flags", lambda _core, _muted: None)
    monkeypatch.setattr(audio_device, "_device_name", lambda _core, dev: f"Device {dev}")
    monkeypatch.setattr(audio_device, "_transport", lambda _core, dev: transports.get(dev, ""))
    monkeypatch.setattr(
        audio_device,
        "_write_volume",
        lambda _core, dev, scalar: written.append((dev, scalar)) or True,
    )


def test_mute_saves_all_device_volumes_and_zeros_them(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(tmp_path / "audio.json"))
    written: list[tuple[int, float]] = []
    volumes = {1: 0.64, 2: 0.88}
    _stub_devices(monkeypatch, volumes, written)
    audio_device.set_output_muted(True)
    assert written == [(1, 0.0), (2, 0.0)]
    written.clear()
    audio_device.set_output_muted(False)
    assert written == [(1, 0.64), (2, 0.88)]


def test_unmute_skips_devices_without_saved_volume(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(tmp_path / "missing.json"))
    written: list[tuple[int, float]] = []
    _stub_devices(monkeypatch, {1: 0.0}, written)
    audio_device.set_output_muted(False)
    assert written == []


def test_mute_keeps_last_good_volume_when_already_quiet(monkeypatch, tmp_path) -> None:
    state = tmp_path / "audio.json"
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(state))
    state.write_text('{"devices": {"80": 0.64, "MacBook Pro Speakers": 0.64}}\n')
    written: list[tuple[int, float]] = []
    _stub_devices(
        monkeypatch,
        {80: 0.0625},
        written,
        transports={80: "bltn"},
    )
    monkeypatch.setattr(audio_device, "_device_name", lambda _core, _dev: "MacBook Pro Speakers")
    audio_device.set_output_muted(True)
    written.clear()
    audio_device.set_output_muted(False)
    assert written == [(80, 0.64)]


def test_unmute_uses_fallback_for_builtin_when_saved_volume_is_a_notch(monkeypatch, tmp_path) -> None:
    state = tmp_path / "audio.json"
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(state))
    state.write_text('{"devices": {"80": 0.0625}}\n')
    written: list[tuple[int, float]] = []
    _stub_devices(
        monkeypatch,
        {80: 0.0},
        written,
        transports={80: "bltn"},
    )
    audio_device.set_output_muted(False)
    assert written == [(80, audio_device._FALLBACK_VOLUME)]
