# mlx is a namespace package (no __init__.py). PyInstaller will not see
# mlx._reprlib_fix unless we list it — mlx.core imports it at init and
# otherwise raises "Encountered an error while initializing the extension."

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

hiddenimports = [
    "mlx._reprlib_fix",
    "mlx.__array_api_info",
    "mlx.utils",
    "mlx.extension",
    "mlx.core",
]
hiddenimports += collect_submodules("mlx.nn")
hiddenimports += collect_submodules("mlx.optimizers")
hiddenimports += collect_submodules("mlx._distributed_utils")

binaries = collect_dynamic_libs("mlx")

datas = []
try:
    import mlx

    root = Path(next(iter(mlx.__path__)))
    for py in root.rglob("*.py"):
        if "__pycache__" in py.parts or "include" in py.parts:
            continue
        dest = str(Path("mlx") / py.relative_to(root).parent)
        datas.append((str(py), dest))
    metallib = root / "lib" / "mlx.metallib"
    if metallib.exists():
        datas.append((str(metallib), "mlx/lib"))
except Exception:
    pass
