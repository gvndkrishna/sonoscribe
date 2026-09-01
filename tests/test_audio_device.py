from sonoscribe import audio_device


def test_mute_saves_all_device_volumes_and_zeros_them(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(tmp_path / "audio.json"))
    written: list[tuple[int, float]] = []
    volumes = {1: 0.64, 2: 0.88}
    monkeypatch.setattr(audio_device, "_core", lambda: "core")
    monkeypatch.setattr(audio_device, "_all_devices", lambda _core: [1, 2])
    monkeypatch.setattr(audio_device, "_read_volume", lambda _core, dev: volumes[dev])
    monkeypatch.setattr(audio_device, "_write_mute_flags", lambda _core, _muted: None)
    monkeypatch.setattr(
        audio_device,
        "_write_volume",
        lambda _core, dev, scalar: written.append((dev, scalar)) or True,
    )
    audio_device.set_output_muted(True)
    assert written == [(1, 0.0), (2, 0.0)]
    written.clear()
    audio_device.set_output_muted(False)
    assert written == [(1, 0.64), (2, 0.88)]


def test_unmute_skips_devices_without_saved_volume(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SONOSCRIBE_AUDIO_STATE", str(tmp_path / "missing.json"))
    written: list[tuple[int, float]] = []
    monkeypatch.setattr(audio_device, "_core", lambda: "core")
    monkeypatch.setattr(audio_device, "_all_devices", lambda _core: [1])
    monkeypatch.setattr(audio_device, "_write_mute_flags", lambda _core, _muted: None)
    monkeypatch.setattr(
        audio_device,
        "_write_volume",
        lambda _core, dev, scalar: written.append((dev, scalar)) or True,
    )
    audio_device.set_output_muted(False)
    assert written == []
