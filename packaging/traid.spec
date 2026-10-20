# PyInstaller spec for the Traid desktop app (run by scripts\build-installer.ps1 from backend\).
# One-folder build: Traid.exe + _internal\ (Python runtime, engine, UI, models, migrations).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # repository root  # noqa: F821 — injected by PyInstaller
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "models" / "manifest.json"), "models"),
    (str(BACKEND / "app" / "migrations"), "app/migrations"),  # Alembic reads the .py scripts
]
datas += [(str(model), "models") for model in (ROOT / "models").glob("*.onnx")]
datas += collect_data_files("webview")

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("alembic")
    + ["sqlalchemy.dialects.sqlite", "multipart", "python_multipart"]
)

a = Analysis(  # noqa: F821
    [str(BACKEND / "app" / "desktop.py")],
    pathex=[str(BACKEND)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "mypy", "ruff", "tkinter", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Traid",
    console=False,
    icon=str(ROOT / "packaging" / "traid.ico"),
    version=str(ROOT / "packaging" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="Traid")  # noqa: F821
