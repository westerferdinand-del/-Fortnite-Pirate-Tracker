"""Notifications « toast » affichées au-dessus du jeu."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import icons
from . import theme as T

OVERLAY_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
                 | Qt.NoDropShadowWindowHint)


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
