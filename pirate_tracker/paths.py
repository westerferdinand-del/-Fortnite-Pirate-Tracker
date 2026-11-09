"""Emplacements des fichiers utilisateur (base de données, réglages, modèles de détection)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Dossier de données : %APPDATA%\\PirateTracker sous Windows, ~/.pirate_tracker ailleurs.

    Peut être forcé via la variable d'environnement PIRATE_TRACKER_HOME (utilisé par les tests).
    """
    override = os.environ.get("PIRATE_TRACKER_HOME")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "PirateTracker"
    else:
        base = Path.home() / ".pirate_tracker"
    base.mkdir(parents=True, exist_ok=True)
    return base


def templates_dir() -> Path:
    d = data_dir() / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def captures_dir() -> Path:
    d = data_dir() / "captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(*parts: str) -> Path:
    """Chemin d'une ressource embarquée (fonctionne aussi dans l'exe PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass) / "pirate_tracker" if meipass else Path(__file__).resolve().parent
    return base.joinpath(*parts)
