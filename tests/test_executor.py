from sonoscribe.executor import KeyboardState, _run_system, run_routine_steps


def test_routine_runs_steps_in_order_with_delay() -> None:
    order: list[str] = []
    keyboard = KeyboardState()
    library = {
        "a": {"id": "a", "name": "A"},
        "b": {"id": "b", "name": "B"},
    }
    routine = {
        "name": "work",
        "steps": [
            {"command_id": "a", "delay_ms": 0},
            {"command_id": "missing", "delay_ms": 0},
            {"command_id": "b", "delay_ms": 0},
        ],
    }
    logs: list[str] = []

    def invoke(command, _keyboard):
        order.append(command["id"])
        return command["name"]

    run_routine_steps(
        routine,
        library.get,
        keyboard,
        logs.append,
        on_command=lambda command, label: None,
        invoke=invoke,
    )
    assert order == ["a", "b"]
    assert any("missing" in line for line in logs)
    assert logs[-1] == "B"


def test_mute_and_unmute_use_coreaudio(monkeypatch) -> None:
    flags: list[bool] = []
    keys: list[int] = []
    monkeypatch.setattr("sonoscribe.executor.set_output_muted", flags.append)
    monkeypatch.setattr("sonoscribe.executor._media_key", keys.append)
    monkeypatch.setattr("sonoscribe.executor.has_bluetooth_output", lambda: False)
    assert _run_system("mute") == "Mute"
    assert _run_system("unmute") == "Unmute"
    assert flags == [True, False]
    assert keys == [7, 7]


def test_mute_sends_volume_keys_for_bluetooth(monkeypatch) -> None:
    keys: list[int] = []
    monkeypatch.setattr("sonoscribe.executor.set_output_muted", lambda _muted: None)
    monkeypatch.setattr("sonoscribe.executor._media_key", keys.append)
    monkeypatch.setattr("sonoscribe.executor.has_bluetooth_output", lambda: True)
    monkeypatch.setattr("sonoscribe.executor.time.sleep", lambda _s: None)
    assert _run_system("mute") == "Mute"
    assert keys[0] == 7
    assert keys[1:] == [1] * 20


def test_volume_steps_use_coreaudio(monkeypatch) -> None:
    deltas: list[float] = []
    monkeypatch.setattr("sonoscribe.executor.adjust_output_volume", deltas.append)
    assert _run_system("volume_up") == "Volume up"
    assert _run_system("volume_down") == "Volume down"
    assert deltas == [0.12, -0.12]
