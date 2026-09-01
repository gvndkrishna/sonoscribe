"""Ensure the frozen mlx namespace can see bundled .py files next to libmlx."""

from __future__ import annotations

import sys
from pathlib import Path


def _meipass() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))


mlx_dir = _meipass() / "mlx"
if mlx_dir.is_dir():
    import mlx

    path = getattr(mlx, "__path__", None)
    if path is not None and str(mlx_dir) not in list(path):
        path.append(str(mlx_dir))
