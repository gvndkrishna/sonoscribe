import numpy as np

from sonoscribe.recorder import Recorder


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


def test_snapshot_clamps_past_end() -> None:
    rec = Recorder()
    rec._chunks = [np.ones(4, dtype=np.float32)]
    rec._length = 4
    snap, end = rec.snapshot(10)
    assert end == 4
    assert snap.size == 0
