from sonoscribe.executor import KeyboardState, _run_system, run_command, run_routine_steps


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
    assert keys == []


def test_mute_sends_volume_keys_for_bluetooth(monkeypatch) -> None:
    keys: list[int] = []
    monkeypatch.setattr("sonoscribe.executor.set_output_muted", lambda _muted: None)
    monkeypatch.setattr("sonoscribe.executor._media_key", keys.append)
    monkeypatch.setattr("sonoscribe.executor.has_bluetooth_output", lambda: True)
    monkeypatch.setattr("sonoscribe.executor.time.sleep", lambda _s: None)
    assert _run_system("mute") == "Mute"
    assert keys == [1] * 20


def test_unmute_restores_hal_before_bluetooth_volume_keys(monkeypatch) -> None:
    order: list[tuple[str, int | bool]] = []
    monkeypatch.setattr(
        "sonoscribe.executor.set_output_muted",
        lambda muted: order.append(("hal", muted)),
    )
    monkeypatch.setattr(
        "sonoscribe.executor._media_key",
        lambda key: order.append(("key", key)),
    )
    monkeypatch.setattr("sonoscribe.executor.has_bluetooth_output", lambda: True)
    monkeypatch.setattr("sonoscribe.executor.time.sleep", lambda _s: None)
    assert _run_system("unmute") == "Unmute"
    assert order[0] == ("hal", False)
    assert order[1:] == [("key", 0)] * 20


def test_app_command_prefers_bundle_id(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("sonoscribe.executor._open", lambda args: calls.append(args))
    label = run_command(
        {
            "type": "app",
            "name": "Safari",
            "app": "Safari",
            "bundle_id": "com.apple.Safari",
        },
        KeyboardState(),
    )
    assert label == "Safari"
    assert calls == [["-b", "com.apple.Safari"]]


def test_app_command_opens_by_name(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("sonoscribe.executor._open", lambda args: calls.append(args))
    run_command({"type": "app", "name": "Notes", "app": "Notes"}, KeyboardState())
    assert calls == [["-a", "Notes"]]


def test_keyboard_plays_recorded_keys(monkeypatch) -> None:
    posts: list[tuple[int, int]] = []
    monkeypatch.setattr("sonoscribe.executor._post_key", lambda vk, flags: posts.append((vk, flags)))
    monkeypatch.setattr("sonoscribe.executor.time.sleep", lambda _s: None)
    label = run_command(
        {
            "type": "keyboard",
            "name": "Save",
            "keys": [{"vk": 1, "mods": ["command"], "label": "⌘S"}],
        },
        KeyboardState(),
    )
    assert label == "Save"
    assert posts[0][0] == 1


def test_script_command_runs_user_bash(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)

    monkeypatch.setattr("sonoscribe.scripts.subprocess.run", fake_run)
    label = run_command(
        {"type": "script", "name": "Hello", "runtime": "bash", "body": "echo hi"},
        KeyboardState(),
    )
    assert label == "Hello"
    assert calls[0][0] == "/bin/bash"


def test_volume_steps_use_coreaudio(monkeypatch) -> None:
    deltas: list[float] = []
    monkeypatch.setattr("sonoscribe.executor.adjust_output_volume", deltas.append)
    assert _run_system("volume_up") == "Volume up"
    assert _run_system("volume_down") == "Volume down"
    assert deltas == [0.12, -0.12]


def test_text_command_inserts_filled_template(monkeypatch) -> None:
    pasted: list[str] = []
    monkeypatch.setattr("sonoscribe.executor.insert", pasted.append)
    keyboard = KeyboardState()
    label = run_command(
        {"type": "text", "name": "Greet", "text": "{hello}"},
        keyboard,
        bindings={"hello": "Greetings guys"},
        variables={"hello": "Greetings guys"},
    )
    assert label == "Greet"
    assert pasted == ["Greetings guys"]
    assert keyboard.last_inserted == "Greetings guys"


def test_app_and_url_fill_bindings(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("sonoscribe.executor._open", lambda args: calls.append(args))
    run_command(
        {"type": "app", "name": "Open", "app": "{1}"},
        KeyboardState(),
        bindings={"1": "Notes"},
    )
    run_command(
        {"type": "website", "name": "Search", "url": "https://example.com/q={*}"},
        KeyboardState(),
        bindings={"*": "hello there"},
        variables={"hello": "Greetings"},
    )
    assert calls[0] == ["-a", "Notes"]
    assert calls[1] == ["https://example.com/q=Greetings there"]
