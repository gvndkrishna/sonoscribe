from sonoscribe.keys import capture_step, chord_label, clean_keys


def test_chord_label_command_t() -> None:
    assert chord_label(0x11, ["command"]) == "⌘T"
    assert chord_label(0x2D, ["command"]) == "⌘N"
    assert chord_label(0x01, ["command", "shift"]) == "⇧⌘S"


def test_capture_step_records_browser_chords() -> None:
    step = capture_step(0x11, command=True, shift=False, option=False, control=False)
    assert step == {"vk": 0x11, "mods": ["command"], "label": "⌘T"}
    step_n = capture_step(0x2D, command=True, shift=False, option=False, control=False)
    assert step_n == {"vk": 0x2D, "mods": ["command"], "label": "⌘N"}


def test_capture_step_ignores_modifiers_and_stops_on_escape() -> None:
    assert capture_step(0x37, command=True, shift=False, option=False, control=False) is None
    assert capture_step(0x35, command=False, shift=False, option=False, control=False) == "stop"
    step = capture_step(0x35, command=True, shift=False, option=False, control=False)
    assert isinstance(step, dict)
    assert step["label"] == "⌘Escape"


def test_clean_keys_keeps_command_t() -> None:
    keys, errors = clean_keys([{"vk": 0x11, "mods": ["command"], "label": "⌘T"}], "Command")
    assert errors == []
    assert keys[0]["vk"] == 0x11
