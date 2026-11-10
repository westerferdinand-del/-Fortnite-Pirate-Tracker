"""Effets visuels : célébration plein écran du jeton pirate et notifications « toast »."""
from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import icons
from . import theme as T

OVERLAY_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
                 | Qt.NoDropShadowWindowHint)


class _Particle:
    __slots__ = ("x", "y", "vx", "vy", "rot", "vr", "size", "kind", "color")

    def __init__(self, w, h):
        self.x = w / 2 + random.uniform(-80, 80)
        self.y = h * 0.45
        ang = random.uniform(-math.pi, 0)
        sp = random.uniform(300, 1100)
        self.vx, self.vy = math.cos(ang) * sp, math.sin(ang) * sp
        self.rot, self.vr = random.uniform(0, 360), random.uniform(-400, 400)
        self.size = random.uniform(14, 34)
        self.kind = random.choice(["coin", "coin", "star", "spark"])
        self.color = random.choice([T.GOLD, "#fde68a", T.VIOLET, "#c4b5fd", T.CYAN])


class TokenCelebration(QWidget):
    """Explosion de pièces et d'étoiles + bannière « JETON PIRATE TROUVÉ ! » (non cliquable)."""

    DURATION = 6.0

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        # 30 img/s et fenêtre limitée au centre : coût minimal pour le jeu en dessous
        self._timer = QTimer(self, interval=33, timeout=self._step)
        self._parts: list[_Particle] = []
        self._t0 = 0.0
        self._last = 0.0
        self.subtitle = ""

    def play(self, chests_before: int) -> None:
        g = QGuiApplication.primaryScreen().geometry()
        w, h = min(1100, int(g.width() * 0.7)), min(720, int(g.height() * 0.75))
        self.setGeometry(g.center().x() - w // 2, g.center().y() - h // 2, w, h)
        self.subtitle = f"Trouvé après {chests_before} coffre{'s' if chests_before > 1 else ''}"
        self._parts = [_Particle(self.width(), self.height()) for _ in range(70)]
        self._t0 = self._last = time.monotonic()
        self.show()
        self.raise_()
        self._timer.start()

    def _step(self) -> None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        for p in self._parts:
            p.vy += 900 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.vr * dt
        if now - self._t0 > self.DURATION:
            self._timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, _):
        el = time.monotonic() - self._t0
        fade = 1.0 if el < self.DURATION - 1 else max(0.0, self.DURATION - el)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(fade)
        w, h = self.width(), self.height()
        # Halo central
        g = QRadialGradient(QPointF(w / 2, h * 0.42), min(w, h) * 0.5)
        g.setColorAt(0, T.c(T.GOLD, int(110 * min(1, el * 3))))
        g.setColorAt(0.5, T.c(T.VIOLET, 50))
        g.setColorAt(1, T.c(T.VIOLET, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(w / 2, h * 0.42), min(w, h) * 0.5, min(w, h) * 0.5)
        # Rayons tournants
        p.save()
        p.translate(w / 2, h * 0.42)
        p.rotate(el * 20)
        p.setPen(Qt.NoPen)
        p.setBrush(T.c(T.GOLD, 30))
        ray = min(w, h) * 0.5
        for i in range(12):
            p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(ray, -ray * 0.12), QPointF(ray, ray * 0.12)]))
            p.rotate(30)
        p.restore()
        # Jeton géant qui pulse
        k = min(1.0, el * 2.5)
        pulse = 1 + 0.05 * math.sin(el * 6)
        size = min(w, h) * 0.32 * k * pulse
        icons.draw_token(p, QRectF(w / 2 - size / 2, h * 0.42 - size / 2, size, size))
        # Particules
        for pt in self._parts:
            p.save()
            p.translate(pt.x, pt.y)
            p.rotate(pt.rot)
            r = QRectF(-pt.size / 2, -pt.size / 2, pt.size, pt.size)
            if pt.kind == "coin":
                p.setPen(QPen(QColor(T.GOLD_D), 2))
                p.setBrush(QColor(T.GOLD))
                p.drawEllipse(QRectF(r.x(), r.y(), r.width(), r.height() * abs(math.cos(math.radians(pt.rot)))))
            elif pt.kind == "star":
                icons.draw_star(p, r, True)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pt.color))
                p.drawEllipse(r.center(), pt.size / 6, pt.size / 6)
            p.restore()
        # Bannière (fond sombre pour rester lisible quel que soit le décor du jeu)
        title = "JETON PIRATE TROUVÉ !"
        size = max(14, int(min(w, h) * 0.075))
        f = T.display_font(size)
        while size > 12 and QFontMetrics(f).horizontalAdvance(title) > w * 0.88:
            size -= 2
            f = T.display_font(size)
        fm = QFontMetrics(f)
        band = QRectF(w * 0.04, h * 0.66, w * 0.92, fm.height() * 1.25 + 40)
        p.setPen(QPen(T.c(T.GOLD, 200), 2))
        p.setBrush(T.c("#0b0718", 225))
        p.drawRoundedRect(band, 18, 18)
        p.setFont(f)
        tr = QRectF(band.x(), band.y() + 6, band.width(), fm.height() * 1.1)
        grad = QLinearGradient(QPointF(w * 0.3, 0), QPointF(w * 0.7, 0))
        grad.setColorAt(0, QColor("#fde68a"))
        grad.setColorAt(0.5, QColor(T.GOLD))
        grad.setColorAt(1, QColor("#fde68a"))
        p.setPen(QPen(grad, 1))
        p.drawText(tr, Qt.AlignCenter, title)
        p.setFont(T.ui_font(max(10, int(size * 0.32)), QFont.Bold))
        p.setPen(QColor(T.TEXT))
        p.drawText(QRectF(band.x(), tr.bottom() - 4, band.width(), 32), Qt.AlignCenter, self.subtitle)
        p.end()


class Toast(QWidget):
    """Petite notification en jeu, en haut à droite, non cliquable."""

    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(360, 76)
        self._queue: list[tuple[str, str, str, float]] = []
        self._current = None
        self._t0 = 0.0
        self._timer = QTimer(self, interval=16, timeout=self._step)

    def notify(self, icon: str, title: str, body: str, duration: float = 2.6) -> None:
        self._queue.append((icon, title, body, duration))
        if self._current is None:
            self._next()

    def _next(self) -> None:
        if not self._queue:
            self._current = None
            self.hide()
            self._timer.stop()
            return
        self._current = self._queue.pop(0)
        g = QGuiApplication.primaryScreen().geometry()
        self.move(g.right() - self.width() - 24, g.top() + 24 + 200)
        self._t0 = time.monotonic()
        self.show()
        self._timer.start()

    def _step(self) -> None:
        if self._current and time.monotonic() - self._t0 > self._current[3]:
            self._next()
        self.update()

    def paintEvent(self, _):
        if not self._current:
            return
        icon, title, body, dur = self._current
        el = time.monotonic() - self._t0
        a = min(1.0, el * 5, max(0.0, (dur - el) * 4))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(a)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        r.translate((1 - a) * 40, 0)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, QColor(30, 18, 64, 240))
        g.setColorAt(1, QColor(10, 14, 40, 240))
        p.setBrush(g)
        p.setPen(QPen(QColor(T.GOLD if icon in ("token", "trophy", "star") else T.VIOLET), 1.6))
        p.drawRoundedRect(r, 12, 12)
        icons.DRAWERS[icon](p, QRectF(r.x() + 14, r.y() + 16, 40, 40))
        p.setPen(QColor(T.GOLD))
        p.setFont(T.display_font(11))
        p.drawText(QRectF(r.x() + 66, r.y() + 12, r.width() - 76, 24), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QColor(T.TEXT))
        p.setFont(T.ui_font(9))
        p.drawText(QRectF(r.x() + 66, r.y() + 38, r.width() - 76, 24), Qt.AlignLeft | Qt.AlignVCenter, body)
        p.end()
