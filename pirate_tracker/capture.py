"""Capture d'écran via les API standard de Windows (les mêmes qu'OBS ou Discord).

* ``dxcam``  : DXGI Desktop Duplication — rapide, fonctionne en plein écran fenêtré
  et généralement en plein écran.
* ``mss``    : GDI BitBlt — universel, un peu plus lent ; image noire possible en
  plein écran exclusif.
* ``video``  : lecture d'un fichier vidéo (validation de la détection hors jeu).

Aucune de ces méthodes ne lit la mémoire du jeu, n'injecte de code ni ne modifie
ses fichiers : on lit uniquement ce qui est affiché à l'écran.
"""
from __future__ import annotations

import sys
import time

import numpy as np


class CaptureError(RuntimeError):
    pass


class Capture:
    name = "base"

    def grab(self) -> np.ndarray | None:  # BGR
        raise NotImplementedError

    def close(self) -> None:
        pass


class MssCapture(Capture):
    name = "mss"

    def __init__(self, monitor: int = 1):
        import mss

        self._sct = mss.mss()
        mons = self._sct.monitors
        if monitor >= len(mons):
            monitor = 1 if len(mons) > 1 else 0
        self.monitor = mons[monitor]

    def grab(self) -> np.ndarray | None:
        shot = self._sct.grab(self.monitor)
        arr = np.asarray(shot)  # BGRA
        return np.ascontiguousarray(arr[..., :3])

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass


class DxcamCapture(Capture):
    name = "dxcam"

    def __init__(self, monitor: int = 1):
        if sys.platform != "win32":
            raise CaptureError("dxcam n'est disponible que sous Windows")
        import dxcam

        self._cam = dxcam.create(output_idx=max(0, monitor - 1), output_color="BGR")
        if self._cam is None:
            raise CaptureError("Impossible d'initialiser DXGI")
        self._last: np.ndarray | None = None

    def grab(self) -> np.ndarray | None:
        frame = self._cam.grab()
        if frame is not None:
            self._last = frame
        return self._last  # dxcam renvoie None si l'écran n'a pas changé

    def close(self) -> None:
        try:
            self._cam.release()
        except Exception:
            pass


class VideoCapture(Capture):
    """Source vidéo : renvoie aussi l'horodatage de chaque image (``last_t``)."""
    name = "video"

    def __init__(self, path: str):
        import cv2

        self._cap = cv2.VideoCapture(str(path))
        if not self._cap.isOpened():
            raise CaptureError(f"Vidéo illisible : {path}")
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._i = 0
        self.last_t = 0.0

    def grab(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        if not ok:
            return None
        self.last_t = self._i / self.fps
        self._i += 1
        return frame

    def skip(self, n: int) -> bool:
        for _ in range(n):
            if not self._cap.grab():
                return False
            self._i += 1
        return True

    def close(self) -> None:
        self._cap.release()


def available_backends() -> list[str]:
    out = []
    if sys.platform == "win32":
        try:
            import dxcam  # noqa: F401

            out.append("dxcam")
        except Exception:
            pass
    try:
        import mss  # noqa: F401

        out.append("mss")
    except Exception:
        pass
    return out


def create_capture(backend: str = "auto", monitor: int = 1) -> Capture:
    order = ["dxcam", "mss"] if backend == "auto" else [backend]
    errors = []
    for b in order:
        try:
            cap = DxcamCapture(monitor) if b == "dxcam" else MssCapture(monitor)
            # Vérifie qu'une image est obtenue
            for _ in range(10):
                if cap.grab() is not None:
                    return cap
                time.sleep(0.05)
            if b == "dxcam":
                return cap  # écran statique : dxcam peut ne rien renvoyer au début
            cap.close()
            errors.append(f"{b}: aucune image")
        except Exception as e:  # pragma: no cover - dépend du système
            errors.append(f"{b}: {e}")
    raise CaptureError("; ".join(errors) or "aucune méthode de capture")


def is_black(frame: np.ndarray | None) -> bool:
    return frame is None or float(frame[::16, ::16].mean()) < 2.0
