# -*- mode: python ; coding: utf-8 -*-
# Construction : pyinstaller packaging/pirate_tracker.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "pirate_tracker", "__main__.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "pirate_tracker", "assets"), os.path.join("pirate_tracker", "assets"))],
    hiddenimports=["dxcam", "comtypes", "comtypes.stream", "PySide6.QtMultimedia"],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
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
