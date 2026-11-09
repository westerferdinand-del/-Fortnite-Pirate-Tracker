"""Détection visuelle du jeton pirate.

Pour distinguer le vrai jeton d'une image ressemblante, trois vérifications
indépendantes doivent toutes réussir, puis être confirmées dans le temps :

1. **Forme** : template matching multi-échelle sur les contours (robuste à la
   luminosité) + niveaux de gris.
2. **Couleur** : corrélation d'histogrammes Teinte/Saturation entre la zone
   candidate et le modèle (un objet de même forme mais d'une autre couleur
   échoue ici) et écart de couleur moyen limité.
3. **Structure fine** : corrélation sur la zone recadrée à l'échelle exacte
   (un logo vaguement similaire échoue ici).
4. **Persistance** : le jeton doit être reconnu sur au moins ``confirm_hits``
   des ``confirm_window`` dernières analyses (élimine les faux positifs d'une
   seule image).

Après une détection, le détecteur se réarme seulement quand le jeton a disparu
de l'écran pendant un moment, pour ne pas compter deux fois la même découverte.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from .common import crop_norm, edge_gray, match_best, to_work

TOKEN_WORK_WIDTH = 1280


@dataclass
class TokenDetectorConfig:
    roi: tuple = (0.0, 0.0, 1.0, 1.0)
    threshold: float = 0.80  # score de forme
    color_threshold: float = 0.55  # corrélation d'histogramme
    max_color_dist: float = 40.0  # distance Lab moyenne
    fine_threshold: float = 0.60
    scales: tuple = tuple(float(x) for x in np.geomspace(0.5, 2.0, 13))  # pas de ~12 %, affiné ensuite
    confirm_window: int = 5
    confirm_hits: int = 3
    rearm_absent: int = 8  # analyses consécutives sans jeton avant de pouvoir re-détecter
    template_width_ref: int = TOKEN_WORK_WIDTH

    @classmethod
    def from_settings(cls, d: dict) -> "TokenDetectorConfig":
        return cls(roi=tuple(d.get("token_roi", cls.roi)), threshold=float(d.get("token_threshold", 0.80)))


@dataclass
class TokenEvent:
    t: float
    confidence: float
    bbox: tuple  # x, y, w, h dans l'image d'origine
    details: dict = field(default_factory=dict)


def _hs_hist(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # On ignore les pixels très sombres / non saturés (fond) qui faussent la couleur
    mask = ((hsv[..., 2] > 40) & (hsv[..., 1] > 30)).astype(np.uint8)
    if mask.sum() < 10:
        mask = None
    hist = cv2.calcHist([hsv], [0, 1], mask, [30, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
    return hist


def _lab_mean(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32).mean(axis=0)


def _soft_edges(img: np.ndarray) -> np.ndarray:
    """Contours légèrement floutés : tolèrent un écart d'échelle de quelques %."""
    return cv2.GaussianBlur(edge_gray(img), (5, 5), 0)


COARSE = 0.5  # recherche grossière à demi-résolution, puis affinage à pleine résolution
MARGIN = 0.10  # bordure du modèle ignorée : elle contient le fond, qui change selon la scène


def _inner(e: np.ndarray) -> tuple[np.ndarray, int, int]:
    h, w = e.shape[:2]
    mx, my = max(1, int(round(w * MARGIN))), max(1, int(round(h * MARGIN)))
    return e[my:h - my, mx:w - mx], mx, my


class _Template:
    def __init__(self, img: np.ndarray, scales):
        self.img = img
        self.hist = _hs_hist(img)
        self.lab = _lab_mean(img)
        self.coarse = []  # (échelle, contours à demi-résolution)
        for s in scales:
            k = s * COARSE
            t = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            if t.shape[0] >= 10 and t.shape[1] >= 10:
                inner, mx, my = _inner(_soft_edges(t))
                self.coarse.append((s, inner, mx, my))

    def at_scale(self, s: float) -> np.ndarray:
        return cv2.resize(self.img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)


class TokenDetector:
    def __init__(self, config: TokenDetectorConfig | None = None, templates: list[np.ndarray] | None = None):
        self.cfg = config or TokenDetectorConfig()
        self.set_templates(templates or [])
        self.reset()

    def set_templates(self, templates: list[np.ndarray]) -> None:
        """Modèles du jeton, à l'échelle de travail (largeur 1280)."""
        self._templates = [_Template(t, self.cfg.scales) for t in templates if t is not None]

    @property
    def has_templates(self) -> bool:
        return bool(self._templates)

    def reset(self) -> None:
        self._hits: deque[bool] = deque(maxlen=self.cfg.confirm_window)
        self._armed = True
        self._absent = 0
        self.metrics: dict = {}

    def analyze(self, frame: np.ndarray) -> tuple[bool, float, tuple, dict]:
        """Analyse une seule image (sans logique temporelle). Retourne (ok, confiance, bbox, détails)."""
        if not self._templates:
            return False, 0.0, (0, 0, 0, 0), {}
        work = to_work(frame, TOKEN_WORK_WIDTH)
        fh, fw = frame.shape[:2]
        k = fw / float(work.shape[1])
        roi = crop_norm(work, self.cfg.roi)
        ox = int(np.clip(self.cfg.roi[0], 0, 1) * work.shape[1])
        oy = int(np.clip(self.cfg.roi[1], 0, 1) * work.shape[0])
        # 1) Recherche grossière, échelles denses, à demi-résolution
        small = cv2.resize(roi, None, fx=COARSE, fy=COARSE, interpolation=cv2.INTER_AREA)
        small_e = _soft_edges(small)
        coarse = (0.0, None, None, 1.0)
        for tpl in self._templates:
            for s, te, mx, my in tpl.coarse:
                sc, (lx, ly) = match_best(small_e, te)
                if sc > coarse[0]:
                    coarse = (sc, tpl, (lx - mx, ly - my), s)
        best = {"shape": 0.0}
        if coarse[1] is not None and coarse[0] >= self.cfg.threshold * 0.75:
            # 2) Affinage à pleine résolution autour du candidat
            _, tpl, (cx, cy), s0 = coarse
            roi_e = _soft_edges(roi)
            roi_g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            for s in (s0 * 0.95, s0 * 0.975, s0, s0 * 1.025, s0 * 1.05):
                timg = tpl.at_scale(s)
                h, w = timg.shape[:2]
                if h < 10 or w < 10:
                    continue
                m = max(6, int(0.25 * max(w, h)))
                x0, y0 = max(0, int(cx / COARSE) - m), max(0, int(cy / COARSE) - m)
                win_e = roi_e[y0:y0 + h + 2 * m, x0:x0 + w + 2 * m]
                inner, mx, my = _inner(_soft_edges(timg))
                se, (lx, ly) = match_best(win_e, inner)
                x, y = max(0, x0 + lx - mx), max(0, y0 + ly - my)
                if roi_g[y:y + h, x:x + w].shape[:2] != (h, w):
                    continue
                sg, _ = match_best(roi_g[y:y + h, x:x + w], cv2.cvtColor(timg, cv2.COLOR_BGR2GRAY))
                shape = 0.65 * se + 0.35 * sg
                if shape > best["shape"]:
                    best = {"shape": shape, "loc": (x, y), "size": (w, h), "tpl": tpl, "timg": timg}

        details = {"shape": best["shape"]}
        if best["shape"] < self.cfg.threshold:
            return False, best["shape"], (0, 0, 0, 0), details

        x, y = best["loc"]
        w, h = best["size"]
        patch = roi[y:y + h, x:x + w]
        tpl: _Template = best["tpl"]
        color = float(cv2.compareHist(_hs_hist(patch), tpl.hist, cv2.HISTCMP_CORREL))
        cdist = float(np.linalg.norm(_lab_mean(patch) - tpl.lab))
        fine, _ = match_best(patch, best["timg"])
        details.update(color=color, color_dist=cdist, fine=fine)
        ok = color >= self.cfg.color_threshold and cdist <= self.cfg.max_color_dist and fine >= self.cfg.fine_threshold
        conf = float(np.clip((best["shape"] + max(0.0, color) + max(0.0, fine)) / 3.0, 0, 1))
        bbox = (int((x + ox) * k), int((y + oy) * k), int(w * k), int(h * k))
        return ok, conf, bbox, details

    def process(self, frame: np.ndarray, t: float) -> TokenEvent | None:
        ok, conf, bbox, details = self.analyze(frame)
        self._hits.append(ok)
        self.metrics = {"t": t, "hit": ok, "confidence": conf, **details,
                        "hits": sum(self._hits), "armed": self._armed}
        if not ok:
            self._absent += 1
            if self._absent >= self.cfg.rearm_absent:
                self._armed = True
            return None
        self._absent = 0
        if self._armed and sum(self._hits) >= self.cfg.confirm_hits:
            self._armed = False
            self._hits.clear()
            return TokenEvent(t, conf, bbox, details)
        return None
