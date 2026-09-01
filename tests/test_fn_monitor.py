from sonoscribe.fn_monitor import TapState, apply_flags, apply_keydown

_VK_FUNCTION = 0x3F
_VK_COMMAND_L = 0x37
_VK_C = 0x08


def test_fn_only_begin_end() -> None:
    state, events = apply_flags(TapState(), True, False, False)
    assert events.begin
    assert not events.command_begin
    state, events = apply_flags(state, False, False, False)
    assert events.end
    assert not events.command_end


def test_fn_plus_cmd_starts_in_command_mode() -> None:
    state, events = apply_flags(TapState(), True, True, False)
    assert events.begin
    assert events.command_begin
    assert not events.cancel
    state, events = apply_flags(state, True, False, False)
    assert events.command_end
    assert not events.end
    state, events = apply_flags(state, False, False, False)
    assert events.end
    assert not events.command_end


def test_cmd_mid_hold_is_command_mode_not_cancel() -> None:
    state, _ = apply_flags(TapState(), True, False, False)
    state, events = apply_flags(state, True, True, False)
    assert events.command_begin
    assert not events.cancel
    state, events = apply_flags(state, True, False, False)
    assert events.command_end
    assert not events.cancel


def test_fn_up_while_cmd_held_ends_command_then_hold() -> None:
    state, _ = apply_flags(TapState(), True, True, False)
    state, events = apply_flags(state, False, True, False)
    assert events.command_end
    assert events.end


def test_shift_cancels_and_fn_up_does_not_end() -> None:
    state, _ = apply_flags(TapState(), True, False, False)
    state, events = apply_flags(state, True, False, True)
    assert events.cancel
    state, events = apply_flags(state, False, False, False)
    assert not events.end
    assert not events.command_end


def test_shift_on_fn_down_does_not_start() -> None:
    _, events = apply_flags(TapState(), True, False, True)
    assert not events.begin
    _, events = apply_flags(TapState(), True, True, True)
    assert not events.begin


def test_command_keydown_does_not_cancel() -> None:
    state, _ = apply_flags(TapState(), True, False, False)
    state, events = apply_keydown(state, _VK_COMMAND_L)
    assert not events.cancel
    state, events = apply_keydown(state, _VK_FUNCTION)
    assert not events.cancel
    _, events = apply_keydown(state, _VK_C)
    assert events.cancel
