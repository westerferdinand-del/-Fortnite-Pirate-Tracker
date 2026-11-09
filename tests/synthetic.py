"""Générateur de séquences vidéo synthétiques « façon Fortnite » pour tester les détecteurs.

Ces images ne remplacent PAS des captures réelles du jeu : elles permettent de
vérifier la logique (machine à états, anti double-comptage, rejet des faux
positifs) de façon reproductible. La validation sur vraies vidéos se fait avec
``tools/validate_video.py``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

W, H = 1280, 720
FPS = 15


@dataclass
class Scene:
    """Chronologie d'une séquence. Tous les temps sont en secondes."""
    duration: float = 6.0
    chest_visible: list = field(default_factory=lambda: [(0.0, 99.0)])
    prompts: list = field(default_factory=list)  # (t0, t1, label)
    opens: list = field(default_factory=list)  # instant d'ouverture (éclat + butin)
    flashes: list = field(default_factory=list)  # explosions dorées sans coffre
    pans: list = field(default_factory=list)  # (t0, t1, pixels/s) mouvement de caméra
    tokens: list = field(default_factory=list)  # (t0, t1, kind, scale) kind: real|recolor|coin
    seed: int = 0


def _background(rng_tex: np.ndarray, offset: float) -> np.ndarray:
    img = np.empty((H, W, 3), np.uint8)
    sky = np.linspace(255, 170, H // 2).astype(np.uint8)
    img[: H // 2, :, 0] = sky[:, None]
    img[: H // 2, :, 1] = (sky[:, None] * 0.8).astype(np.uint8)
    img[: H // 2, :, 2] = (sky[:, None] * 0.55).astype(np.uint8)
    img[H // 2:, :] = (50, 120, 60)
    shift = int(offset) % rng_tex.shape[1]
    tex = np.roll(rng_tex, -shift, axis=1)[:, :W]
    img = cv2.add(img, tex)
    # arbres / bâtiments qui défilent avec la caméra
    for i in range(12):
        x = int((i * 173 - offset) % (W + 200)) - 100
        cv2.rectangle(img, (x, 220 + (i * 37) % 80), (x + 60, H // 2 + 40), (40 + i * 5, 70, 90 + i * 3), -1)
    return img


def _hud(img: np.ndarray) -> None:
    cv2.rectangle(img, (W - 210, 20), (W - 20, 210), (60, 60, 60), -1)  # minicarte
    cv2.rectangle(img, (40, H - 70), (360, H - 52), (80, 200, 80), -1)  # vie
    cv2.rectangle(img, (40, H - 45), (360, H - 27), (220, 160, 60), -1)  # bouclier
    for i in range(5):
        cv2.rectangle(img, (W - 520 + i * 90, H - 100), (W - 440 + i * 90, H - 20), (90, 90, 90), 2)


def draw_prompt(img: np.ndarray, label: str = "Coffre", action: str = "Fouiller") -> None:
    x, y = int(W * 0.60), int(H * 0.58)
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + 230, y + 70), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)
    cv2.rectangle(img, (x + 10, y + 12), (x + 46, y + 48), (240, 240, 240), 2)
    cv2.putText(img, "E", (x + 18, y + 41), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, action, (x + 58, y + 38), cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, label, (x + 58, y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA)


def _chest(img: np.ndarray, t: float, opened_at: float | None, cx: int) -> None:
    cy = int(H * 0.56)
    opened = opened_at is not None and t >= opened_at
    cv2.rectangle(img, (cx - 70, cy - 30), (cx + 70, cy + 40), (30, 70, 120), -1)
    cv2.rectangle(img, (cx - 70, cy - 30), (cx + 70, cy + 40), (40, 180, 230), 3)
    if opened:
        pts = np.array([[cx - 70, cy - 30], [cx + 70, cy - 30], [cx + 60, cy - 90], [cx - 60, cy - 90]])
        cv2.fillPoly(img, [pts], (30, 70, 120))
    else:
        cv2.rectangle(img, (cx - 74, cy - 55), (cx + 74, cy - 30), (30, 80, 140), -1)
        # lueur dorée permanente d'un coffre fermé (scintillement léger)
        glow = 0.5 + 0.5 * math.sin(t * 6)
        r = int(18 + 6 * glow)
        cv2.circle(img, (cx, cy - 10), r, (60, 200, 250), -1)
        for k in range(6):
            a = t * 2 + k
            cv2.circle(img, (cx + int(60 * math.cos(a)), cy - 20 + int(25 * math.sin(a))), 3, (80, 220, 255), -1)


def _burst(img: np.ndarray, dt: float, cx: int, cy: int, rng: np.random.Generator) -> None:
    """Éclat doré + butin qui jaillit, pendant ~1,2 s après l'ouverture."""
    if dt < 0 or dt > 1.6:
        return
    strength = math.exp(-dt * 2.2)
    radius = int(60 + 260 * min(1.0, dt / 0.35))
    layer = np.zeros_like(img)
    cv2.circle(layer, (cx, cy), radius, (40, 200, 255), -1)
    layer = cv2.GaussianBlur(layer, (0, 0), 25)
    cv2.addWeighted(img, 1.0, layer, 0.95 * strength, 0, img)
    for k in range(5):
        col = [(180, 180, 180), (60, 200, 60), (230, 140, 40), (220, 60, 200), (40, 190, 255)][k]
        ang = -math.pi / 2 + (k - 2) * 0.5
        d = 220 * min(1.0, dt / 0.8)
        px, py = int(cx + d * math.cos(ang)), int(cy - 40 + d * math.sin(ang) * 0.6 + 120 * max(0, dt - 0.5))
        cv2.rectangle(img, (px - 14, py - 14), (px + 14, py + 14), col, -1)
    for _ in range(int(40 * strength)):
        px = int(cx + rng.normal(0, 90))
        py = int(cy + rng.normal(-40, 60))
        cv2.circle(img, (px, py), 2, (120, 240, 255), -1)


def _flash(img: np.ndarray, dt: float) -> None:
    if dt < 0 or dt > 0.8:
        return
    s = math.exp(-dt * 4)
    layer = np.zeros_like(img)
    cv2.circle(layer, (W // 2 + 40, H // 2), 220, (30, 150, 255), -1)
    layer = cv2.GaussianBlur(layer, (0, 0), 35)
    cv2.addWeighted(img, 1.0, layer, s, 0, img)


def token_image(kind: str = "real", size: int = 96) -> np.ndarray:
    """Icône du « jeton pirate » synthétique (pièce violette avec tête de mort dorée).

    kind="recolor": même dessin mais vert (image ressemblante d'une autre couleur)
    kind="coin": pièce dorée ordinaire (forme ronde, motif différent)
    """
    img = np.full((size, size, 3), (25, 15, 20), np.uint8)
    c = size // 2
    r = int(size * 0.44)
    if kind == "coin":
        cv2.circle(img, (c, c), r, (30, 180, 230), -1)
        cv2.circle(img, (c, c), int(r * 0.75), (20, 140, 200), 3)
        cv2.putText(img, "$", (c - size // 7, c + size // 7), cv2.FONT_HERSHEY_SIMPLEX, size / 60, (20, 120, 180), 3)
        return img
    body = (170, 40, 120) if kind == "real" else (60, 160, 40)
    rim = (40, 200, 250) if kind == "real" else (200, 220, 220)
    cv2.circle(img, (c, c), r, body, -1)
    cv2.circle(img, (c, c), r, rim, max(2, size // 24))
    # tête de mort
    cv2.circle(img, (c, c - size // 12), size // 6, rim, -1)
    cv2.rectangle(img, (c - size // 10, c), (c + size // 10, c + size // 7), rim, -1)
    cv2.circle(img, (c - size // 16, c - size // 10), size // 22, body, -1)
    cv2.circle(img, (c + size // 16, c - size // 10), size // 22, body, -1)
    cv2.line(img, (c - r // 2, c + r // 2), (c + r // 2, c + r // 5), rim, max(2, size // 20))
    cv2.line(img, (c + r // 2, c + r // 2), (c - r // 2, c + r // 5), rim, max(2, size // 20))
    return img


def render(scene: Scene):
    """Génère (t, image BGR) pour toute la scène."""
    rng = np.random.default_rng(scene.seed)
    tex = rng.integers(0, 25, size=(H, W * 2, 3), dtype=np.uint8)
    tex = cv2.GaussianBlur(tex, (0, 0), 2)
    offset = 0.0
    n = int(scene.duration * FPS)
    for i in range(n):
        t = i / FPS
        for (p0, p1, speed) in scene.pans:
            if p0 <= t < p1:
                offset += speed / FPS
        offset += 2.0 * math.sin(t * 1.3)  # léger balancement permanent
        img = _background(tex, offset)
        cx = int(W * 0.5 - (offset % 10000) * 0.0)  # le coffre suit le centre sauf en panoramique
        pan_shift = sum(max(0.0, min(t, p1) - p0) * s for (p0, p1, s) in scene.pans if t >= p0)
        cx = int(W // 2 - pan_shift)
        last_open = max([o for o in scene.opens if o <= t], default=None)
        if any(a <= t < b for a, b in scene.chest_visible) and -200 < cx < W + 200:
            _chest(img, t, last_open, cx)
        for o in scene.opens:
            _burst(img, t - o, cx, int(H * 0.5), rng)
        for f in scene.flashes:
            _flash(img, t - f)
        for (p0, p1, label) in scene.prompts:
            if p0 <= t < p1:
                draw_prompt(img, label=label)
        for (k0, k1, kind, scale) in scene.tokens:
            if k0 <= t < k1:
                tok = token_image(kind, int(96 * scale))
                th, tw = tok.shape[:2]
                y0, x0 = int(H * 0.30), int(W * 0.42)
                img[y0:y0 + th, x0:x0 + tw] = tok
        _hud(img)
        noise = rng.normal(0, 3, img.shape).astype(np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        yield t, img


def prompt_template_from_scene(label: str = "Coffre") -> np.ndarray:
    """Simule le calibrage : capture d'écran avec l'invite, découpe, mise à l'échelle de travail."""
    from pirate_tracker.detection.common import WORK_WIDTH

    scene = Scene(duration=0.5, prompts=[(0, 1, label)], seed=99)
    _, frame = next(iter(render(scene)))
    x, y = int(W * 0.60), int(H * 0.58)
    crop = frame[y:y + 70, x:x + 230]
    k = WORK_WIDTH / W
    return cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)


def write_video(scene: Scene, path: str) -> str:
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for _, img in render(scene):
        vw.write(img)
    vw.release()
    return path
