"""Détection du processus Fortnite et de la fenêtre au premier plan.

Lecture seule de la liste des processus (comme le Gestionnaire des tâches) :
aucune interaction avec le processus du jeu.
"""
from __future__ import annotations

import sys

FORTNITE_EXES = {"fortniteclient-win64-shipping.exe", "fortniteclient-win64-shipping_eac.exe",
                 "fortniteclient-win64-shipping_eac_eos.exe", "fortniteclient-win64-shipping_be.exe"}


def _proc_names():
    import psutil

    for p in psutil.process_iter(["name"]):
        try:
            yield (p.info.get("name") or "").lower(), p.pid
        except Exception:
            continue


def fortnite_pid(extra_names: set[str] | None = None) -> int | None:
    names = FORTNITE_EXES | {n.lower() for n in (extra_names or set())}
    for name, pid in _proc_names():
        if name in names:
            return pid
    return None


def foreground_pid() -> int | None:
    """PID de la fenêtre active (Windows uniquement). None si inconnu."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


def fortnite_is_foreground(pid: int | None) -> bool | None:
    fg = foreground_pid()
    if fg is None or pid is None:
        return None
    return fg == pid
