"""Microphone capture as 16 kHz mono float32 for Whisper."""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000
MINIMUM_SAMPLES = int(SAMPLE_RATE * 0.3)


class RecorderError(RuntimeError):
    pass


class Recorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._length = 0
        self._stream: sd.InputStream | None = None

    def start(self) -> None:
        self.stop()
        with self._lock:
            self._chunks = []
            self._length = 0

        def callback(indata, frames, time, status) -> None:  # noqa: ARG001
            if status:
                pass
            with self._lock:
                self._chunks.append(np.copy(indata[:, 0]))
                self._length += indata.shape[0]

        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=callback,
            )
            stream.start()
        except Exception as exc:  # noqa: BLE001
            raise RecorderError(f"Could not open the microphone: {exc}") from exc
        self._stream = stream

    def cursor(self) -> int:
        with self._lock:
            return self._length

    def copy_range(self, start: int, end: int | None = None) -> np.ndarray:
        with self._lock:
            return self._copy_range_locked(start, end)

    def snapshot(self, start: int) -> tuple[np.ndarray, int]:
        """Copy `[start, cursor)` under one lock. Returns `(samples, end)`."""
        with self._lock:
            end = self._length
            return self._copy_range_locked(start, end), end

    def _copy_range_locked(self, start: int, end: int | None) -> np.ndarray:
        total = self._length
        if end is None:
            end = total
        start = max(0, min(int(start), total))
        end = max(start, min(int(end), total))
        if start == end:
            return np.zeros(0, dtype=np.float32)
        parts: list[np.ndarray] = []
        offset = 0
        for chunk in self._chunks:
            next_off = offset + chunk.size
            if next_off <= start:
                offset = next_off
                continue
            if offset >= end:
                break
            a = max(0, start - offset)
            b = min(chunk.size, end - offset)
            parts.append(chunk[a:b])
            offset = next_off
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts).astype(np.float32, copy=False)

    def stop(self) -> np.ndarray:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            audio = self._copy_range_locked(0, self._length)
            self._chunks = []
            self._length = 0
        return audio
