"""Boucle de détection en arrière-plan (thread) : capture → détecteurs → évènements."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import process_watch
from .capture import CaptureError, create_capture, is_black
from .detection import ChestDetector, ChestDetectorConfig, TokenDetector, TokenDetectorConfig
from .detection.templates import TemplateStore

ACTIVE, CONFIGURING, INACTIVE = "active", "configuring", "inactive"


@dataclass
class EngineStatus:
    level: str = INACTIVE  # active / configuring / inactive
    message: str = "Détection inactive"
    fortnite_running: bool = False
    fortnite_foreground: bool | None = None
    backend: str = ""
    fps: float = 0.0
    chest_mode: str = ""


class DetectionEngine:
    """Thread de détection. Les callbacks sont appelés depuis ce thread."""

    def __init__(self, settings: dict, templates: TemplateStore,
                 on_chest: Callable | None = None, on_token: Callable | None = None,
                 on_status: Callable | None = None, on_metrics: Callable | None = None,
                 on_fortnite: Callable | None = None):
        self.settings = settings
        self.templates = templates
        self.on_chest = on_chest
        self.on_token = on_token
        self.on_status = on_status
        self.on_metrics = on_metrics
        self.on_fortnite = on_fortnite
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = EngineStatus()
        self.last_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()
        self._build_detectors()

    # ------------------------------------------------------------------ control
    def _build_detectors(self) -> None:
        d = self.settings
        self.chest = ChestDetector(ChestDetectorConfig.from_settings(d), self.templates.load("prompt"))
        self.token = TokenDetector(TokenDetectorConfig.from_settings(d), self.templates.load("token"))

    def reload(self) -> None:
        """À appeler après un changement de réglages ou de modèles."""
        self._reload.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="detection", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    def snapshot(self) -> np.ndarray | None:
        with self._frame_lock:
            return None if self.last_frame is None else self.last_frame.copy()

    # ------------------------------------------------------------------ loop
    def _set_status(self, level: str, message: str, **kw) -> None:
        changed = (level, message) != (self.status.level, self.status.message)
        self.status.level, self.status.message = level, message
        for k, v in kw.items():
            setattr(self.status, k, v)
        if changed and self.on_status:
            self.on_status(self.status)

    def _run(self) -> None:
        cap = None
        last_proc_check = 0.0
        pid = None
        last_token_t = 0.0
        frames, fps_t0 = 0, time.monotonic()
        last_metrics = 0.0
        try:
            while not self._stop.is_set():
                if self._reload.is_set():
                    self._reload.clear()
                    self._build_detectors()
                    if cap:
                        cap.close()
                        cap = None
                d = self.settings
                now = time.monotonic()

                if now - last_proc_check > 2.0:
                    last_proc_check = now
                    new_pid = process_watch.fortnite_pid()
                    if (new_pid is not None) != self.status.fortnite_running and self.on_fortnite:
                        self.on_fortnite(new_pid is not None)
                    pid = new_pid
                    self.status.fortnite_running = pid is not None
                    self.status.fortnite_foreground = process_watch.fortnite_is_foreground(pid)

                if not d.get("enabled", True):
                    self._set_status(INACTIVE, "Détection désactivée dans les paramètres")
                    self._sleep(0.5)
                    continue
                if d.get("only_when_fortnite_running", True) and not self.status.fortnite_running:
                    self._set_status(INACTIVE, "En attente du lancement de Fortnite…")
                    self.chest.reset()
                    self._sleep(1.0)
                    continue
                if self.status.fortnite_foreground is False:
                    # Fortnite en arrière-plan : on ne compte pas ce qui est à l'écran (ex. une vidéo YouTube)
                    self._set_status(CONFIGURING, "Fortnite n'est pas au premier plan — détection en pause")
                    self.chest.reset()
                    self._sleep(0.5)
                    continue

                if cap is None:
                    try:
                        cap = create_capture(d.get("capture_backend", "auto"), int(d.get("monitor", 1)))
                        self.status.backend = cap.name
                    except CaptureError as e:
                        self._set_status(CONFIGURING, f"Capture d'écran impossible : {e}")
                        self._sleep(3.0)
                        continue

                frame = cap.grab()
                if is_black(frame):
                    self._set_status(CONFIGURING, "Image noire : passez Fortnite en « Plein écran fenêtré »")
                    self._sleep(0.5)
                    continue
                with self._frame_lock:
                    self.last_frame = frame

                t = time.monotonic()
                ev = self.chest.process(frame, t)
                mode = self.chest.effective_mode
                if mode == "prompt+burst":
                    self._set_status(ACTIVE, "Détection active", chest_mode=mode)
                else:
                    msg = ("Détection active (mode éclat seul)" if d.get("chest_mode") == "burst"
                           else "Calibrage conseillé : capturez l'invite « Fouiller » (mode éclat seul en attendant)")
                    self._set_status(ACTIVE if d.get("chest_mode") == "burst" else CONFIGURING, msg, chest_mode=mode)
                if ev and self.on_chest:
                    self.on_chest(ev)

                if d.get("token_enabled", True) and self.token.has_templates:
                    if t - last_token_t >= 1.0 / max(0.5, float(d.get("token_fps", 3))):
                        last_token_t = t
                        tev = self.token.process(frame, t)
                        if tev and self.on_token:
                            self.on_token(tev, frame)

                frames += 1
                if t - fps_t0 >= 1.0:
                    self.status.fps = frames / (t - fps_t0)
                    frames, fps_t0 = 0, t
                if self.on_metrics and t - last_metrics > 0.1:
                    last_metrics = t
                    self.on_metrics({**self.chest.metrics, "token": dict(self.token.metrics), "fps": self.status.fps})

                target = 1.0 / max(1.0, float(d.get("fps", 15)))
                self._sleep(max(0.0, target - (time.monotonic() - now)))
        finally:
            if cap:
                cap.close()
            self._set_status(INACTIVE, "Détection arrêtée")

    def _sleep(self, s: float) -> None:
        if s > 0:
            self._stop.wait(s)


def analyze_video(path: str, settings: dict, templates: TemplateStore, fps: float | None = None,
                  progress: Callable[[float], None] | None = None, stop: threading.Event | None = None) -> dict:
    """Passe une vidéo enregistrée dans les détecteurs (validation hors jeu).

    Retourne les horodatages (secondes dans la vidéo) des coffres et jetons détectés.
    """
    from .capture import VideoCapture

    vc = VideoCapture(path)
    fps = fps or float(settings.get("fps", 15))
    step = max(1, int(round(vc.fps / fps)))
    chest = ChestDetector(ChestDetectorConfig.from_settings(settings), templates.load("prompt"))
    token = TokenDetector(TokenDetectorConfig.from_settings(settings), templates.load("token"))
    token_step = max(1, int(round(fps / max(0.5, float(settings.get("token_fps", 3))))))
    chests, tokens = [], []
    i = 0
    try:
        while True:
            if stop and stop.is_set():
                break
            frame = vc.grab()
            if frame is None:
                break
            t = vc.last_t
            ev = chest.process(frame, t)
            if ev:
                chests.append({"t": round(t, 2), "confidence": round(ev.confidence, 2), "method": ev.method})
            if token.has_templates and i % token_step == 0:
                tev = token.process(frame, t)
                if tev:
                    tokens.append({"t": round(t, 2), "confidence": round(tev.confidence, 2)})
            i += 1
            if progress and vc.frame_count and i % 20 == 0:
                progress(min(1.0, i * step / vc.frame_count))
            if not vc.skip(step - 1):
                break
    finally:
        vc.close()
    return {"chests": chests, "tokens": tokens, "mode": chest.effective_mode, "frames": i}
