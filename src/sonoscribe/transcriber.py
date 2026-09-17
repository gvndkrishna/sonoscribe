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
from pathlib import Path
from typing import Any

import numpy as np

from sonoscribe.actions import TimedWord

DEFAULT_MODEL = "large-v3-turbo"
MODELS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "small": "mlx-community/whisper-small",
    "base": "mlx-community/whisper-base",
}
MODEL_LABELS = {
    "large-v3-turbo": "large v3 turbo",
    "small": "small",
    "base": "base",
}
MODEL_HINTS = {
    "large-v3-turbo": "high",
    "small": "balanced",
    "base": "fast",
}
_WEIGHT_NAMES = ("weights.npz", "weights.safetensors", "model.safetensors")


def clean_model(value: Any, fallback: str = DEFAULT_MODEL, custom_ids: Any = ()) -> str:
    key = str(value or "").strip()
    allowed = set(MODELS)
    allowed.update(str(item) for item in (custom_ids or ()) if item)
    if key in allowed:
        return key
    return fallback if fallback in allowed else DEFAULT_MODEL


def custom_model_id(path: str) -> str:
    import hashlib

    resolved = str(Path(path).expanduser().resolve())
    return "custom-" + hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:10]


def normalize_model_dir(path: str) -> Path:
    folder = Path(str(path or "").strip()).expanduser()
    if folder.is_file():
        folder = folder.parent
    return folder.resolve()


def local_model_error(path: str) -> str | None:
    raw = str(path or "").strip()
    if not raw:
        return "Folder required."
    try:
        folder = normalize_model_dir(raw)
    except OSError:
        return "That folder could not be read."
    if not folder.is_dir():
        return "Choose a model folder."
    if not (folder / "config.json").is_file():
        return "That folder has no config.json."
    has_weights = any((folder / name).is_file() for name in _WEIGHT_NAMES) or any(
        folder.glob("*.npz")
    ) or any(folder.glob("*.safetensors"))
    if not has_weights:
        return "That folder has no weights."
    return None


def model_is_cached(model_key: str) -> bool:
    repo = MODELS.get(model_key)
    if not repo:
        return False
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(repo_id=repo, local_files_only=True)
    except Exception:
        return False
    return True


def public_models(custom_models: Any = None) -> list[dict[str, Any]]:
    items = [
        {
            "id": key,
            "label": MODEL_LABELS[key],
            "hint": MODEL_HINTS[key],
            "cached": model_is_cached(key),
            "custom": False,
            "path": "",
        }
        for key in MODELS
    ]
    for item in custom_models or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or "").strip()
        path = str(item.get("path") or "").strip()
        if not key or not path:
            continue
        items.append(
            {
                "id": key,
                "label": str(item.get("name") or Path(path).name),
                "hint": "custom",
                "cached": Path(path).expanduser().is_dir(),
                "custom": True,
                "path": path,
            }
        )
    return items


def model_label(key: str, custom_models: Any = None) -> str:
    if key in MODEL_LABELS:
        return MODEL_LABELS[key]
    for item in custom_models or []:
        if isinstance(item, dict) and str(item.get("id") or "") == key:
            return str(item.get("name") or key)
    return key or DEFAULT_MODEL


def friendly_load_error(exc: BaseException | str) -> str:
    if isinstance(exc, BaseException):
        name = type(exc).__name__
        text = str(exc)
    else:
        name = ""
        text = str(exc)
    blob = f"{name} {text}".lower()
    if "could not download" in blob or "add a local model" in blob:
        first = text.strip().splitlines()[0] if text.strip() else "Could not load model."
        return first[:160]
    if (
        "401" in text
        or "invalid username or password" in blob
        or "repositorynotfound" in blob
        or "localentrynotfound" in blob
        or "outgoing traffic has been disabled" in blob
    ):
        return "Could not download. Add a local model folder."
    first = text.strip().splitlines()[0] if text.strip() else "Could not load model."
    if len(first) > 160:
        return first[:157] + "…"
    return first


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


def worker_command(model_key: str, model_path: str | None = None) -> list[str]:
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--worker"]
    else:
        cmd = [sys.executable, "-m", "sonoscribe", "--worker"]
    path = str(model_path or "").strip()
    if path:
        cmd.extend(["--model-path", path])
        return cmd
    cmd.extend(["--model", model_key])
    return cmd


class Transcriber:
    def __init__(self, model_key: str = DEFAULT_MODEL, model_path: str | None = None) -> None:
        self.model_key = DEFAULT_MODEL
        self.model_path: str | None = None
        self.repo = MODELS[DEFAULT_MODEL]
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._apply_source(model_key, model_path)

    def _apply_source(self, model_key: str, model_path: str | None) -> None:
        path = str(model_path or "").strip() or None
        if path:
            error = local_model_error(path)
            if error:
                raise TranscribeError(error)
            folder = str(normalize_model_dir(path))
            self.model_key = str(model_key or "").strip() or custom_model_id(folder)
            self.model_path = folder
            self.repo = ""
            return
        key = str(model_key or "").strip()
        if key not in MODELS:
            known = ", ".join(MODELS)
            raise TranscribeError(f"Unknown model {key!r}. Choose one of: {known}")
        self.model_key = key
        self.model_path = None
        self.repo = MODELS[key]

    def is_ready(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def set_model(self, model_key: str, model_path: str | None = None) -> None:
        with self._lock:
            path = str(model_path or "").strip() or None
            if (
                str(model_key) == self.model_key
                and path == self.model_path
                and self.is_ready()
            ):
                return
            previous_key = self.model_key
            previous_path = self.model_path
            try:
                self._apply_source(model_key, path)
            except Exception:
                self._apply_source(previous_key, previous_path)
                raise
            try:
                self._load_locked()
            except Exception:
                try:
                    self._apply_source(previous_key, previous_path)
                    self._load_locked()
                except Exception:
                    pass
                raise

    def load(self) -> None:
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        self.close()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            worker_command(self.model_key, self.model_path),
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
                raise TranscribeError(friendly_load_error(str(data["error"])))

    def transcribe(self, samples: np.ndarray) -> Transcript:
        if samples.size == 0:
            raise TranscribeError("No audio was captured.")

        fd, path = tempfile.mkstemp(prefix="sonoscribe-", suffix=".npy")
        os.close(fd)
        try:
            np.save(path, np.ascontiguousarray(samples, dtype=np.float32))
            with self._lock:
                if self._proc is None or self._proc.poll() is not None:
                    raise TranscribeError("The Whisper worker is not running.")
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
