"""Parent-side Whisper client. Inference runs in an isolated MLX worker process."""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import tempfile
import threading

from dataclasses import dataclass

import numpy as np

from sonoscribe.actions import TimedWord

MODELS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "small": "mlx-community/whisper-small",
    "base": "mlx-community/whisper-base",
}


def resolve_model_path(repo: str) -> str:
    """Use a cached Hugging Face snapshot when present; download only if missing.

    mlx-whisper otherwise calls snapshot_download on every load, which contacts
    the Hub even when weights are already on disk (and fails behind Zscaler).
    """
    from huggingface_hub import snapshot_download

    try:
        return snapshot_download(repo_id=repo, local_files_only=True)
    except Exception:
        return snapshot_download(repo_id=repo)


class TranscribeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Transcript:
    text: str
    words: tuple[TimedWord, ...] = ()


def worker_command(model_key: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker", "--model", model_key]
    return [sys.executable, "-m", "sonoscribe", "--worker", "--model", model_key]


class Transcriber:
    def __init__(self, model_key: str = "large-v3-turbo") -> None:
        if model_key not in MODELS:
            known = ", ".join(MODELS)
            raise TranscribeError(f"Unknown model {model_key!r}. Choose one of: {known}")
        self.model_key = model_key
        self.repo = MODELS[model_key]
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        self.close()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            worker_command(self.model_key),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,
        )
        self._proc = proc
        atexit.register(self.close)
        threading.Thread(target=self._forward_stderr, daemon=True).start()

        assert proc.stdout is not None
        while True:
            line = proc.stdout.readline()
            if not line:
                raise TranscribeError(self._exit_error("Worker exited before the model was ready."))
            payload = line.strip()
            if payload == "WORKER_LOADING":
                continue
            if payload == "WORKER_READY":
                return
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if "error" in data:
                raise TranscribeError(data["error"])

    def transcribe(self, samples: np.ndarray) -> Transcript:
        if self._proc is None or self._proc.poll() is not None:
            raise TranscribeError("The Whisper worker is not running.")
        if samples.size == 0:
            raise TranscribeError("No audio was captured.")

        fd, path = tempfile.mkstemp(prefix="sonoscribe-", suffix=".npy")
        os.close(fd)
        try:
            np.save(path, np.ascontiguousarray(samples, dtype=np.float32))
            with self._lock:
                assert self._proc.stdin is not None and self._proc.stdout is not None
                self._proc.stdin.write(path + "\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            if not line:
                raise TranscribeError(self._exit_error("Whisper worker died during transcription."))
            data = json.loads(line)
            if "error" in data:
                raise TranscribeError(data["error"])
            words = tuple(
                TimedWord(
                    str(item.get("word", "")),
                    float(item.get("start") or 0),
                    float(item.get("end") or 0),
                )
                for item in data.get("words") or []
                if str(item.get("word", "")).strip()
            )
            return Transcript(text=str(data.get("text", "")).strip(), words=words)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write("QUIT\n")
                proc.stdin.flush()
                proc.stdin.close()
                proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()

    def _forward_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()

    def _exit_error(self, prefix: str) -> str:
        proc = self._proc
        detail = ""
        if proc is not None and proc.poll() is not None:
            detail = f" Exit code {proc.returncode}."
        return (
            f"{prefix}{detail} "
            "This usually means MLX failed to start Metal. "
            "Try `uv run python -c 'import mlx.core as mx; print(mx.default_device())'`."
        )
