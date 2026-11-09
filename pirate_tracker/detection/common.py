"""Outils d'image partagés par les détecteurs."""
from __future__ import annotations

import cv2
import numpy as np

WORK_WIDTH = 960  # toutes les analyses de coffre se font à cette largeur


def to_work(frame: np.ndarray, width: int = WORK_WIDTH) -> np.ndarray:
    h, w = frame.shape[:2]
    if w == width:
        return frame
    scale = width / float(w)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    return cv2.resize(frame, (width, max(1, int(round(h * scale)))), interpolation=interp)


def crop_norm(frame: np.ndarray, roi) -> np.ndarray:
    """Découpe une région normalisée (x, y, w, h) dans [0, 1]."""
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    x0 = int(np.clip(x, 0, 1) * w)
    y0 = int(np.clip(y, 0, 1) * h)
    x1 = int(np.clip(x + rw, 0, 1) * w)
    y1 = int(np.clip(y + rh, 0, 1) * h)
    if x1 <= x0 or y1 <= y0:
        return frame[0:1, 0:1]
    return frame[y0:y1, x0:x1]


def gold_mask(bgr: np.ndarray) -> np.ndarray:
    """Pixels dorés/jaunes lumineux (lueur et éclat des coffres)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (h >= 12) & (h <= 35) & (s >= 100) & (v >= 160)


def edge_gray(bgr: np.ndarray) -> np.ndarray:
    """Représentation robuste aux variations de luminosité pour le template matching."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    g = cv2.GaussianBlur(g, (3, 3), 0)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    return cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def match_best(image: np.ndarray, templ: np.ndarray) -> tuple[float, tuple[int, int]]:
    if image.shape[0] < templ.shape[0] or image.shape[1] < templ.shape[1]:
        return 0.0, (0, 0)
    res = cv2.matchTemplate(image, templ, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if not np.isfinite(mx):
        return 0.0, (0, 0)
    return float(mx), loc


def cell_scores(patch: np.ndarray, templ: np.ndarray, rows: int = 2, cols: int = 3, min_std: float = 8.0) -> list[float]:
    """Corrélation cellule par cellule entre une zone et le modèle (mêmes dimensions).

    Un modèle peut correspondre globalement alors qu'une petite partie diffère
    (ex. « Coffre » vs « Caisse de munitions » sous la même invite « Fouiller ») :
    la plus faible cellule texturée révèle cette différence.
    """
    h, w = templ.shape[:2]
    if patch.shape[:2] != templ.shape[:2]:
        return []
    out = []
    for i in range(rows):
        for j in range(cols):
            y0, y1 = i * h // rows, (i + 1) * h // rows
            x0, x1 = j * w // cols, (j + 1) * w // cols
            tc = templ[y0:y1, x0:x1].astype(np.float32)
            pc = patch[y0:y1, x0:x1].astype(np.float32)
            if tc.size < 16 or tc.std() < min_std:
                continue
            tc -= tc.mean()
            pc -= pc.mean()
            den = float(np.sqrt((tc * tc).sum() * (pc * pc).sum()))
            out.append(float((tc * pc).sum() / den) if den > 1e-6 else 0.0)
    return out
