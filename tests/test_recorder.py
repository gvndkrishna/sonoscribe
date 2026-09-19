import numpy as np

from sonoscribe.recorder import COMMAND_PREROLL, Recorder, attach_preroll, take_command_preroll


def test_copy_range_spans_chunks() -> None:
    rec = Recorder()
    rec._chunks = [
        np.arange(0, 10, dtype=np.float32),
        np.arange(10, 20, dtype=np.float32),
    ]
    rec._length = 20
    assert rec.cursor() == 20
    got = rec.copy_range(5, 15)
    np.testing.assert_array_equal(got, np.arange(5, 15, dtype=np.float32))
    snap, end = rec.snapshot(8)
    assert end == 20
    np.testing.assert_array_equal(snap, np.arange(8, 20, dtype=np.float32))
    assert rec.copy_range(20, 20).size == 0
    assert rec.copy_range(-3, 4).tolist() == [0.0, 1.0, 2.0, 3.0]


def test_short_leftover_stays_on_command() -> None:
    short = np.ones(COMMAND_PREROLL // 2, dtype=np.float32)
    preroll, dictate = take_command_preroll(short)
    assert dictate is None
    assert preroll.size == short.size
    long = np.ones(COMMAND_PREROLL + 10, dtype=np.float32)
    preroll, dictate = take_command_preroll(long)
    assert preroll.size == 0
    assert dictate is not None and dictate.size == long.size
    joined = attach_preroll(short, np.ones(4, dtype=np.float32))
    assert joined.size == short.size + 4


def test_snapshot_clamps_past_end() -> None:
    rec = Recorder()
    rec._chunks = [np.ones(4, dtype=np.float32)]
    rec._length = 4
    snap, end = rec.snapshot(10)
    assert end == 4
    assert snap.size == 0
