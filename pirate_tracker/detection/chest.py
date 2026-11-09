"""Détection automatique des ouvertures de coffre.

Principe (mode ``prompt+burst``, recommandé) :

1. **Invite d'interaction** – quand le joueur vise un coffre fermé, Fortnite affiche
   l'invite « Fouiller / Search » (touche + texte). Elle est reconnue par
   *template matching* sur une petite région de l'écran, à partir d'un modèle
   capturé une fois par l'utilisateur (calibrage : langue, résolution et échelle
   de l'interface diffèrent d'un joueur à l'autre).
2. **Disparition de l'invite** – à l'ouverture, l'invite disparaît instantanément
   (un coffre ouvert n'a plus d'invite : c'est ce qui évite de confondre coffre
   ouvert et coffre fermé, et de compter deux fois le même coffre).
3. **Éclat d'ouverture** – l'animation d'ouverture produit un éclat doré et
   l'apparition du butin au centre de l'écran. On mesure (a) le saut du taux de
   pixels dorés par rapport à une ligne de base lente – la lueur permanente d'un
   coffre fermé est absorbée par cette ligne de base. Ce saut est obligatoire.
   (b) un changement *localisé* au centre de l'image renforce le score, sans
   jamais suffire seul (un panoramique de caméra le déclencherait aussi).

Un coffre n'est compté que si 1 → 2 → 3 se produisent dans cet ordre et dans une
fenêtre de temps courte. Un délai de récupération (cooldown) empêche tout
double comptage.

Mode ``burst`` (sans calibrage) : seul l'éclat 3 est utilisé, avec un seuil plus
strict. Moins fiable (explosions, objets dorés…), proposé comme solution de repli.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from .common import cell_scores, crop_norm, edge_gray, gold_mask, match_best, to_work


@dataclass
class ChestDetectorConfig:
    mode: str = "prompt+burst"  # ou "burst"
    prompt_roi: tuple = (0.52, 0.48, 0.30, 0.30)
    burst_roi: tuple = (0.30, 0.25, 0.40, 0.50)
    prompt_threshold: float = 0.72
    prompt_hysteresis: float = 0.12
    prompt_min_time: float = 0.20  # l'invite doit être vue au moins ce temps
    verify_before: float = 0.35  # l'éclat peut commencer juste avant la disparition
    verify_after: float = 1.20  # ... ou jusqu'à ce délai après
    cooldown: float = 2.5
    sensitivity: float = 1.0  # >1 = plus sensible
    gold_jump_ref: float = 0.035  # saut du taux de pixels dorés = score 1
    local_change_ref: float = 10.0  # (centre - périphérie) en niveaux de gris = score 1
    burst_only_factor: float = 1.6  # sévérité supplémentaire du mode sans invite
    min_gold_burst_only: float = 0.04
    scales: tuple = (0.92, 1.0, 1.08)

    @classmethod
    def from_settings(cls, d: dict) -> "ChestDetectorConfig":
        return cls(
            mode=d.get("chest_mode", "prompt+burst"),
            prompt_roi=tuple(d.get("prompt_roi", cls.prompt_roi)),
            burst_roi=tuple(d.get("burst_roi", cls.burst_roi)),
            prompt_threshold=float(d.get("prompt_threshold", 0.72)),
            sensitivity=float(d.get("burst_sensitivity", 1.0)),
            cooldown=float(d.get("cooldown_s", 2.5)),
        )


@dataclass
class ChestEvent:
    t: float
    confidence: float
    method: str
    details: dict = field(default_factory=dict)


IDLE, ARMED, VERIFY, COOLDOWN = "idle", "armed", "verify", "cooldown"


class ChestDetector:
    def __init__(self, config: ChestDetectorConfig | None = None, prompt_templates: list[np.ndarray] | None = None):
        self.cfg = config or ChestDetectorConfig()
        self.set_templates(prompt_templates or [])
        self.reset()

    # ------------------------------------------------------------------ setup
    def set_templates(self, templates: list[np.ndarray]) -> None:
        """Modèles de l'invite, déjà à l'échelle de travail (largeur 960)."""
        self._templates: list[tuple[np.ndarray, np.ndarray]] = []
        for t in templates:
            for s in self.cfg.scales:
                tt = t if s == 1.0 else cv2.resize(t, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                if tt.shape[0] < 6 or tt.shape[1] < 6:
                    continue
                gray = cv2.cvtColor(tt, cv2.COLOR_BGR2GRAY)
                self._templates.append((gray, edge_gray(tt)))

    @property
    def has_templates(self) -> bool:
        return bool(self._templates)

    @property
    def effective_mode(self) -> str:
        return self.cfg.mode if (self.cfg.mode == "burst" or self.has_templates) else "burst"

    def reset(self) -> None:
        self.state = IDLE
        self._prompt_since: float | None = None
        self._prompt_gone_at: float | None = None
        self._low_frames = 0
        self._cooldown_until = -1e9
        self._baseline: float | None = None
        self._prev_small: np.ndarray | None = None
        self._burst_hist: deque[tuple[float, float]] = deque(maxlen=64)
        self._burst_run = 0
        self.metrics: dict = {}

    # ------------------------------------------------------------------ measures
    def prompt_score(self, work: np.ndarray) -> float:
        if not self._templates:
            return 0.0
        roi = crop_norm(work, self.cfg.prompt_roi)
        g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        e = edge_gray(roi)
        best = 0.0
        for tg, te in self._templates:
            sg, loc = match_best(g, tg)
            se, _ = match_best(e, te)
            score = 0.4 * sg + 0.6 * se
            if score <= best:
                continue
            # Vérification fine : chaque partie texturée du modèle doit aussi correspondre
            x, y = loc
            h, w = tg.shape[:2]
            cells = cell_scores(g[y:y + h, x:x + w], tg, rows=3, cols=4)
            if cells:
                score = min(score, min(cells))
            best = max(best, score)
        return best

    def _burst_measures(self, work: np.ndarray) -> tuple[float, float, float, float]:
        roi = crop_norm(work, self.cfg.burst_roi)
        small_roi = cv2.resize(roi, (128, max(8, int(128 * roi.shape[0] / max(1, roi.shape[1])))),
                               interpolation=cv2.INTER_AREA)
        gold = float(gold_mask(small_roi).mean())

        small = cv2.cvtColor(cv2.resize(work, (96, 54), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        small = small.astype(np.float32)
        local = 0.0
        global_change = 0.0
        if self._prev_small is not None:
            diff = np.abs(small - self._prev_small)
            x, y, w, h = self.cfg.burst_roi
            cx0, cy0 = int(x * 96), int(y * 54)
            cx1, cy1 = int((x + w) * 96), int((y + h) * 54)
            center = diff[cy0:cy1, cx0:cx1]
            mask = np.ones_like(diff, dtype=bool)
            mask[cy0:cy1, cx0:cx1] = False
            periph = diff[mask]
            c = float(center.mean()) if center.size else 0.0
            p = float(periph.mean()) if periph.size else 0.0
            local = max(0.0, c - 1.2 * p)
            global_change = float(diff.mean())
        self._prev_small = small
        brightness = float(small.mean())
        return gold, local, global_change, brightness

    # ------------------------------------------------------------------ main
    def process(self, frame: np.ndarray, t: float) -> ChestEvent | None:
        """Analyse une image (BGR, n'importe quelle résolution) prise au temps ``t`` (secondes)."""
        work = to_work(frame)
        gold, local, global_change, brightness = self._burst_measures(work)

        # Écran noir / chargement / changement de scène total : on ignore.
        invalid = brightness < 8 or global_change > 60

        if self._baseline is None:
            self._baseline = gold
        gold_jump = max(0.0, gold - self._baseline)
        # L'éclat doré est obligatoire ; le changement localisé ne fait que renforcer le score
        # (seul, il est trompé par les mouvements de caméra : le HUD fixe calme la périphérie).
        local_boost = 1.0 + 0.5 * min(1.0, local / self.cfg.local_change_ref)
        burst = 0.0 if invalid else self.cfg.sensitivity * (gold_jump / self.cfg.gold_jump_ref) * local_boost
        # La ligne de base suit lentement (la lueur d'un coffre fermé), mais pas pendant un éclat.
        if burst < 0.6:
            self._baseline += 0.05 * (gold - self._baseline)
        self._burst_hist.append((t, burst))

        mode = self.effective_mode
        pscore = self.prompt_score(work) if mode == "prompt+burst" else 0.0

        self.metrics = {
            "t": t, "state": self.state, "mode": mode, "prompt": pscore, "gold": gold,
            "baseline": self._baseline, "gold_jump": gold_jump, "local": local,
            "global": global_change, "burst": burst,
        }

        if t < self._cooldown_until:
            self.state = COOLDOWN
            return None
        if self.state == COOLDOWN:
            self.state = IDLE
            self._prompt_since = None

        if mode == "burst":
            return self._step_burst_only(t, gold, burst)
        return self._step_prompt(t, pscore)

    def _max_burst(self, t0: float, t1: float) -> float:
        vals = [b for (tt, b) in self._burst_hist if t0 <= tt <= t1]
        return max(vals) if vals else 0.0

    def _emit(self, t: float, conf: float, method: str, **details) -> ChestEvent:
        self._cooldown_until = t + self.cfg.cooldown
        self.state = COOLDOWN
        self._prompt_since = None
        self._prompt_gone_at = None
        self._burst_run = 0
        return ChestEvent(t, float(min(1.0, conf)), method, details)

    def _step_prompt(self, t: float, pscore: float) -> ChestEvent | None:
        hi = self.cfg.prompt_threshold
        lo = hi - self.cfg.prompt_hysteresis
        if self.state == IDLE:
            if pscore >= hi:
                if self._prompt_since is None:
                    self._prompt_since = t
                if t - self._prompt_since >= self.cfg.prompt_min_time:
                    self.state = ARMED
                    self._low_frames = 0
            else:
                self._prompt_since = None
            return None

        if self.state == ARMED:
            if pscore < lo:
                self._low_frames += 1
                if self._low_frames == 1:
                    self._prompt_gone_at = t
                if self._low_frames >= 2:
                    self.state = VERIFY
            else:
                self._low_frames = 0
                return None

        if self.state == VERIFY:
            gone = self._prompt_gone_at if self._prompt_gone_at is not None else t
            b = self._max_burst(gone - self.cfg.verify_before, t)
            if b >= 1.0:
                return self._emit(t, 0.6 + 0.2 * min(2.0, b), "prompt+burst", burst=b, prompt_gone=gone)
            if pscore >= hi:  # l'invite revient : simple scintillement
                self.state = ARMED
                self._low_frames = 0
                return None
            if t - gone > self.cfg.verify_after:  # le joueur s'est éloigné sans ouvrir
                self.state = IDLE
                self._prompt_since = None
        return None

    def _step_burst_only(self, t: float, gold: float, burst: float) -> ChestEvent | None:
        strict = burst / self.cfg.burst_only_factor
        if strict >= 1.0 and gold >= self.cfg.min_gold_burst_only:
            self._burst_run += 1
        else:
            self._burst_run = 0
        if self._burst_run >= 2:
            return self._emit(t, 0.4 + 0.15 * min(2.0, strict), "burst", burst=burst)
        return None
