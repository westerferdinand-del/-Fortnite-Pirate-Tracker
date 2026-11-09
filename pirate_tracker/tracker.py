"""Logique métier : sessions, compteur automatique, niveaux, records, jetons.

Indépendant de l'interface graphique : reçoit les évènements du moteur de
détection, les enregistre en base et notifie les abonnés.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

from . import levels
from .config import Config
from .database import Database
from .detection.templates import imwrite_unicode
from .paths import captures_dir


class Tracker:
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self.session_id: int | None = None
        self._lock = threading.RLock()
        self.listeners: list[Callable[[str, dict], None]] = []
        self._last_heartbeat = 0.0
        self._best_session_before = 0

    # ------------------------------------------------------------------ pub/sub
    def subscribe(self, fn: Callable[[str, dict], None]) -> None:
        self.listeners.append(fn)

    def _emit(self, kind: str, payload: dict | None = None) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, payload or {})
            except Exception:  # un abonné défaillant ne doit pas casser le comptage
                import traceback

                traceback.print_exc()

    # ------------------------------------------------------------------ sessions
    def start_session(self) -> int:
        with self._lock:
            if self.session_id is None:
                self._best_session_before = self.db.stats().best_session
                self.session_id = self.db.start_session()
                self._emit("session_started", {"session_id": self.session_id})
            return self.session_id

    def end_session(self) -> None:
        with self._lock:
            if self.session_id is not None:
                sid = self.session_id
                self.db.end_session(sid)
                self.session_id = None
                self._emit("session_ended", {"session_id": sid})

    def heartbeat(self) -> None:
        if self.session_id is not None and time.time() - self._last_heartbeat > 15:
            self._last_heartbeat = time.time()
            self.db.heartbeat(self.session_id)

    def on_fortnite(self, running: bool) -> None:
        if running:
            self.start_session()
        else:
            self.end_session()
        self._emit("fortnite", {"running": running})

    # ------------------------------------------------------------------ events
    @property
    def thresholds(self) -> list[int]:
        return self.config.get("levels", "star_thresholds", [10, 25, 50, 100, 200])

    def record_chest(self, confidence: float = 1.0, method: str = "auto") -> dict:
        with self._lock:
            if self.session_id is None:
                self.start_session()
            before = self.db.total_chests()
            self.db.add_chest(self.session_id, confidence, method)
            after = before + 1
            stats = self.db.stats(self.session_id)
            payload = {"total": after, "confidence": confidence, "method": method, "stats": stats}
            self._emit("chest", payload)

            for kind, st in levels.transitions(before, after, self.thresholds):
                self.db.add_level_event(kind, st.level, st.stars, after)
                self._emit(kind, {"level": st.level, "stars": st.stars, "total": after})

            # Nouveau record : la session en cours dépasse la meilleure session précédente
            if self._best_session_before > 0 and stats.session_chests == self._best_session_before + 1:
                self._emit("record", {"session_chests": stats.session_chests, "previous": self._best_session_before})
            self.heartbeat()
            return payload

    def record_token(self, confidence: float, frame=None, bbox=None) -> dict:
        with self._lock:
            if self.session_id is None:
                self.start_session()
            shot = None
            if frame is not None:
                import cv2

                img = frame.copy()
                if bbox and bbox[2] > 0:
                    x, y, w, h = bbox
                    cv2.rectangle(img, (x - 4, y - 4), (x + w + 4, y + h + 4), (0, 215, 255), 3)
                path = captures_dir() / f"jeton_{datetime.now():%Y%m%d_%H%M%S}.png"
                if imwrite_unicode(path, img):
                    shot = str(path)
            info = self.db.add_token(self.session_id, confidence, shot)
            payload = {**info, "confidence": confidence, "screenshot": shot, "stats": self.db.stats(self.session_id)}
            self._emit("token", payload)
            return payload

    def undo_last_chest(self) -> bool:
        with self._lock:
            ok = self.db.remove_last_chest()
            if ok:
                self._emit("chest_removed", {"stats": self.db.stats(self.session_id)})
            return ok

    def reset_all(self) -> None:
        with self._lock:
            had = self.session_id is not None
            self.session_id = None
            self.db.reset()
            if had:
                self.session_id = self.db.start_session()
            self._best_session_before = 0
            self._emit("reset", {"stats": self.db.stats(self.session_id)})

    def stats(self):
        return self.db.stats(self.session_id)

    def level(self) -> levels.LevelState:
        return levels.compute_level(self.db.total_chests(), self.thresholds)
