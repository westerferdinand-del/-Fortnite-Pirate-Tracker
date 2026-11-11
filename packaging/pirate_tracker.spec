# -*- mode: python ; coding: utf-8 -*-
# Construction : pyinstaller packaging/pirate_tracker.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Lecteur de replays C# publié au préalable (voir .github/workflows/windows-build.yml)
READER = os.path.join(ROOT, "build", "reader", "PirateReplayReader.exe")
if not os.path.exists(READER):
    raise SystemExit("PirateReplayReader.exe manquant : lancez d'abord dotnet publish (voir README)")

a = Analysis(
    [os.path.join(ROOT, "pirate_tracker", "__main__.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "pirate_tracker", "assets"), os.path.join("pirate_tracker", "assets")),
           (os.path.join(ROOT, "pirate_tracker", "companion", "web"), os.path.join("pirate_tracker", "companion", "web"))],
    binaries=[(READER, os.path.join("pirate_tracker", "bin"))],
    hiddenimports=["PySide6.QtMultimedia", "qrcode", "qrcode.constants"],
    excludes=["tkinter", "matplotlib", "numpy", "cv2", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
              "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PirateTracker",
    icon=os.path.join(ROOT, "pirate_tracker", "assets", "icon.ico"),
    console=False,
    upx=False,
    version=os.path.join(SPECPATH, "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PirateTracker")
