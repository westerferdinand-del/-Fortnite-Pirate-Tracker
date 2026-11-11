"""Réglages persistants (JSON) de l'application."""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from .paths import data_dir

DEFAULTS: dict[str, Any] = {
    "replays": {
        "enabled": True,
        "demos_dir": "",  # vide = dossier par défaut de Fortnite
        # Les replays plus anciens que cette date (installation) ne sont pas comptés
        # automatiquement : ils peuvent être importés depuis la page Replays.
        "count_since": 0,
    },
    "token": {
        # Motifs (expressions régulières) du nom interne de l'objet « jeton pirate »
        "patterns": [r"pirate.*(token|coin|doubloon|medal|jeton)", r"(token|coin|doubloon|medal|jeton).*pirate"],
        # Noms internes exacts désignés par l'utilisateur dans la page Récompenses
        "items": [],
        # Taux publié par Epic : 1 chance sur N par coffre (partie normale, hors Treasure Hours)
        "one_in": 137500,
    },
    # Application mobile : page servie sur le réseau local (désactivée par défaut)
    "companion": {
        "enabled": False,
        "port": 8765,
        "token": "",
    },
    "overlay": {
        "visible": True,
        "size": "medium",  # small | medium | large
        "position": "top-center",  # top-left | top-center | top-right | bottom-left | bottom-right | custom
        "custom_pos": [100, 40],
        "opacity": 0.85,
        "accent": "#8b5cf6",
    },
    "notifications": {
        "enabled": True,
        "on_match": True,
        "on_token": True,
        "on_level": True,
        "on_record": True,
    },
    "sound": {
        "enabled": True,
        "volume": 0.7,
        "match_sound": "",  # vide = son intégré
        "token_sound": "",
        "level_sound": "",
    },
    # Coffres (depuis le début du niveau) nécessaires pour chaque étoile. 5 étoiles = niveau suivant.
    "levels": {
        "star_thresholds": [10, 25, 50, 100, 200],
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self._lock = threading.Lock()
        self.data: dict[str, Any] = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self.data = _merge(DEFAULTS, json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                self.data = deepcopy(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any, save: bool = True) -> None:
        self.data.setdefault(section, {})[key] = value
        if save:
            self.save()

    def section(self, name: str) -> dict[str, Any]:
        return self.data.setdefault(name, {})
