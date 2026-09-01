# PyInstaller onedir spec. Do not collect_all('mlx') — that double-registers mlx.core.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH)

hiddenimports = [
    "sonoscribe",
    "sonoscribe.app",
    "sonoscribe.cleaner",
    "sonoscribe.commands",
    "sonoscribe.actions",
    "sonoscribe.lexicon",
    "sonoscribe.fn_monitor",
    "sonoscribe.inserter",
    "sonoscribe.permissions",
    "sonoscribe.recorder",
    "sonoscribe.runtime",
    "sonoscribe.transcriber",
    "sonoscribe.catalog",
    "sonoscribe.executor",
    "sonoscribe.audio_device",
    "sonoscribe.stats",
    "sonoscribe.dashboard",
    "sonoscribe.dashboard.server",
    "sonoscribe.worker",
    "mlx",
    "mlx.core",
    "mlx._reprlib_fix",
    "mlx.__array_api_info",
    "mlx.utils",
    "mlx.nn",
    "mlx.optimizers",
    "sounddevice",
    "numpy",
    "tiktoken",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    "truststore",
    "huggingface_hub",
    "AppKit",
    "Quartz",
    "ApplicationServices",
    "Foundation",
    "CoreFoundation",
    "objc",
    "PyObjCTools",
    "PyObjCTools.AppHelper",
]
hiddenimports += collect_submodules("mlx.nn")
hiddenimports += collect_submodules("mlx.optimizers")
hiddenimports += collect_submodules("mlx._distributed_utils")
hiddenimports += collect_submodules("mlx_whisper")

binaries = []
datas = []

binaries += collect_dynamic_libs("mlx")
datas += collect_data_files("mlx", includes=["**/*.metallib"])
datas += collect_data_files("mlx_whisper")

dash_static = ROOT / "src" / "sonoscribe" / "dashboard" / "static"
if dash_static.is_dir():
    datas.append((str(dash_static), "sonoscribe/dashboard/static"))

try:
    import mlx

    mlx_root = Path(next(iter(mlx.__path__)))
    for py in mlx_root.rglob("*.py"):
        if "__pycache__" in py.parts or "include" in py.parts:
            continue
        dest = str(Path("mlx") / py.relative_to(mlx_root).parent)
        datas.append((str(py), dest))
except Exception:
    pass

try:
    binaries += collect_dynamic_libs("sounddevice")
    datas += collect_data_files("sounddevice")
    datas += collect_data_files("_sounddevice_data")
    binaries += collect_dynamic_libs("_sounddevice_data")
except Exception:
    pass

try:
    datas += collect_data_files("tiktoken")
    datas += collect_data_files("tiktoken_ext")
except Exception:
    pass

a = Analysis(
    [str(ROOT / "src" / "sonoscribe" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[
        str(ROOT / "hooks" / "pyi_rth_sslcert.py"),
        str(ROOT / "hooks" / "pyi_rth_mlx.py"),
    ],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sonoscribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="sonoscribe",
)

app = BUNDLE(
    coll,
    name="Sonoscribe.app",
    icon=None,
    bundle_identifier="dev.sonoscribe.app",
    version="0.1.0",
    codesign_identity=None,
    info_plist={
        "CFBundleName": "Sonoscribe",
        "CFBundleDisplayName": "Sonoscribe",
        "CFBundleIdentifier": "dev.sonoscribe.app",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSMinimumSystemVersion": "14.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "NSMicrophoneUsageDescription": (
            "Sonoscribe records while you hold Fn so it can transcribe on this Mac."
        ),
    },
)
