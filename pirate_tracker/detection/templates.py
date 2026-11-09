"""Gestion des modèles visuels (invite « Fouiller » et icône du jeton) capturés par l'utilisateur."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

KINDS = ("prompt", "token")


def imread_unicode(path: Path) -> np.ndarray | None:
    """cv2.imread ne gère pas les chemins Unicode sous Windows : on passe par numpy."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, img: np.ndarray) -> bool:
    ok, buf = cv2.imencode(Path(path).suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return bool(ok)


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        for k in KINDS:
            (self.root / k).mkdir(parents=True, exist_ok=True)

    def dir(self, kind: str) -> Path:
        assert kind in KINDS
        return self.root / kind

    def list(self, kind: str) -> list[Path]:
        return sorted(p for p in self.dir(kind).glob("*.png"))

    def load(self, kind: str) -> list[np.ndarray]:
        out = []
        for p in self.list(kind):
            img = imread_unicode(p)
            if img is not None and img.shape[0] >= 8 and img.shape[1] >= 8:
                out.append(img)
        return out

    def add(self, kind: str, img: np.ndarray, name: str | None = None) -> Path:
        name = name or f"{kind}_{int(time.time() * 1000)}"
        path = self.dir(kind) / f"{name}.png"
        imwrite_unicode(path, img)
        return path

    def remove(self, path: Path) -> None:
        Path(path).unlink(missing_ok=True)

    def count(self, kind: str) -> int:
        return len(self.list(kind))
