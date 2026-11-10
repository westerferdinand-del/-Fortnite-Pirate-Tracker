"""Logique métier : enregistre chaque partie analysée, niveaux, records, jetons pirates.

Indépendant de l'interface : reçoit les résultats du lecteur de replays et notifie les abonnés.
"""
from __future__ import annotations

import threading
from typing import Callable

from . import items as items_mod
from . import levels
from .config import Config
from .database import Database


class Tracker:
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self._lock = threading.RLock()
        self.listeners: list[Callable[[str, dict], None]] = []

    # ------------------------------------------------------------------ pub/sub
    def subscribe(self, fn: Callable[[str, dict], None]) -> None:
        self.listeners.append(fn)

    def _emit(self, kind: str, payload: dict | None = None) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, payload or {})
            except Exception:  # un abonné défaillant ne doit pas casser l'enregistrement
                import traceback

                traceback.print_exc()

    # ------------------------------------------------------------------ réglages
    @property
    def thresholds(self) -> list[int]:
        return self.config.get("levels", "star_thresholds", [10, 25, 50, 100, 200])

    def token_matcher(self) -> Callable[[str], bool]:
        t = self.config.section("token")
        patterns = t.get("patterns", items_mod.DEFAULT_TOKEN_PATTERNS)
        exact = t.get("items", [])
        return lambda raw: items_mod.is_token(raw, patterns, exact)

    # ------------------------------------------------------------------ parties
    def record_match(self, res: dict, size: int | None = None, mtime: float | None = None,
                     notify: bool = True) -> dict:
        """Enregistre le résultat d'un replay et déclenche niveaux / records / jetons."""
        size = res.get("_size", 0) if size is None else size
        mtime = res.get("_mtime", 0.0) if mtime is None else mtime
        with self._lock:
            before_total = self.db.total_chests()
            best_before = self.db.stats().best_match
            info = self.db.upsert_match(res, size, mtime)
            after_total = self.db.total_chests()

            tokens = []
            is_token = self.token_matcher()
            for it in info["items"]:
                if is_token(it.get("item", "")):
                    tok = self.db.add_token(info["match_id"], it["item"], info["started_at"] + float(it.get("t", 0)))
                    tokens.append({**tok, "item": it["item"]})
                    break  # un seul jeton par partie suffit à marquer la découverte

            payload = {**info, "ok": bool(res.get("ok")), "error": res.get("error"),
                       "warnings": res.get("warnings") or [], "placement": res.get("placement"),
                       "total": after_total, "tokens": tokens, "notify": notify}
            self._emit("match", payload)
            if not notify:
                return payload

            for kind, st in levels.transitions(before_total, after_total, self.thresholds):
                self.db.add_level_event(kind, st.level, st.stars, after_total)
                self._emit(kind, {"level": st.level, "stars": st.stars, "total": after_total})
            if best_before > 0 and info["chests"] > best_before and not info["replaced"]:
                self._emit("record", {"match_chests": info["chests"], "previous": best_before})
            for tok in tokens if not info["replaced"] else []:
                self._emit("token", {**tok, "stats": self.db.stats()})
            return payload

    def import_results(self, results: list[dict]) -> int:
        """Import en masse (anciens replays) : pas de notification pour chaque partie."""
        before = self.db.total_chests()
        for r in sorted(results, key=lambda r: r.get("started_utc") or ""):
            self.record_match(r, notify=False)
        after = self.db.total_chests()
        for kind, st in levels.transitions(before, after, self.thresholds):
            self.db.add_level_event(kind, st.level, st.stars, after)
        self._emit("imported", {"count": len(results), "chests": after - before})
        return after - before

    def mark_token_item(self, raw: str, on: bool) -> None:
        """L'utilisateur désigne (ou retire) un objet comme étant le jeton pirate."""
        exact = list(self.config.get("token", "items", []))
        if on and raw not in exact:
            exact.append(raw)
        if not on and raw in exact:
            exact.remove(raw)
        self.config.set("token", "items", exact)
        self.rebuild_tokens()

    def rebuild_tokens(self) -> None:
        """Recalcule les découvertes de jetons à partir des objets enregistrés."""
        is_token = self.token_matcher()
        with self._lock:
            conn = self.db.conn
            with self.db._lock:
                conn.execute("DELETE FROM token_events")
                conn.commit()
            rows = conn.execute("SELECT match_id, ts, item FROM items ORDER BY ts").fetchall()
            done = set()
            for r in rows:
                if r["match_id"] not in done and is_token(r["item"]):
                    done.add(r["match_id"])
                    self.db.add_token(r["match_id"], r["item"], r["ts"])
        self._emit("tokens_rebuilt", {})

    def set_initial_chests(self, n: int) -> None:
        """Coffres ouverts avant l'installation : ajoutés au total, sans déclencher d'étoiles en rafale."""
        self.db.set_initial_chests(n)
        self._emit("initial_changed", {"total": self.db.total_chests()})

    def delete_match(self, match_id: int) -> None:
        self.db.delete_match(match_id)
        self._emit("match_removed", {"match_id": match_id})

    def reset_all(self) -> None:
        with self._lock:
            self.db.reset()
            self._emit("reset", {})

    def stats(self):
        return self.db.stats()

    def level(self) -> levels.LevelState:
        return levels.compute_level(self.db.total_chests(), self.thresholds)
