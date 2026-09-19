"""MLX Whisper process with no AppKit/Quartz — Metal init cannot share a process with Cocoa."""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from sonoscribe.runtime import configure_tls
from sonoscribe.transcriber import MODELS, friendly_load_error, resolve_model_path


def parse_job(line: str) -> tuple[str, str]:
    text = str(line or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text, "dictate"
        if isinstance(data, dict):
            path = str(data.get("path") or "")
            mode = str(data.get("mode") or "dictate")
            return path, mode
    return text, "dictate"


def transcribe_options(_mode: str) -> dict[str, Any]:
    return {
        "language": "en",
        "word_timestamps": True,
        "condition_on_previous_text": False,
    }


def run_worker(model_key: str | None = None, model_path: str | None = None) -> int:
    source = str(model_path or "").strip() or None
    key = str(model_key or "").strip()
    try:
        print("WORKER_LOADING", flush=True)
        configure_tls()
        import mlx.core as mx  # noqa: F401
        import mlx_whisper
        from mlx_whisper.load_models import load_model

        if source:
            model_dir = source
        else:
            repo = MODELS[key or "large-v3-turbo"]
            model_dir = resolve_model_path(repo)
        load_model(model_dir)
        print("WORKER_READY", flush=True)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(json.dumps({"error": friendly_load_error(exc)}), flush=True)
        return 1

    import numpy as np

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line or line == "QUIT":
            break
        try:
            audio_path, mode = parse_job(line)
            if not audio_path:
                print(json.dumps({"error": "No audio path."}), flush=True)
                continue
            samples = np.load(audio_path)
            result = mlx_whisper.transcribe(
                np.ascontiguousarray(samples, dtype=np.float32),
                path_or_hf_repo=model_dir,
                **transcribe_options(mode),
            )
            text = result.get("text", "") if isinstance(result, dict) else str(result)
            words = []
            if isinstance(result, dict):
                for segment in result.get("segments") or []:
                    for item in segment.get("words") or []:
                        token = str(item.get("word", "")).strip()
                        if not token:
                            continue
                        words.append(
                            {
                                "word": token,
                                "start": float(item.get("start") or 0),
                                "end": float(item.get("end") or 0),
                            }
                        )
            print(json.dumps({"text": str(text).strip(), "words": words}), flush=True)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), flush=True)
    return 0
