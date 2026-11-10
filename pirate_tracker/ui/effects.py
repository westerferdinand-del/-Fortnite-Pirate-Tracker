"""Notifications v2 : petite carte sobre en haut à droite, au-dessus du jeu, non cliquable."""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme as T

OVERLAY_FLAGS = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
                 | Qt.NoDropShadowWindowHint)


class Toast(QWidget):
    def __init__(self):
        super().__init__(None, OVERLAY_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(320, 64)
        self._queue: list[tuple[str, str, float]] = []
        self._current: tuple[str, str, float] | None = None
        self._t0 = 0.0
        self._timer = QTimer(self, interval=16, timeout=self._step)

    def notify(self, title: str, body: str = "", duration: float = 3.0) -> None:
        self._queue.append((title, body, duration))
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
        self.move(g.right() - self.width() - 20, g.top() + 20)
        self._t0 = time.monotonic()
        self.show()
        self._timer.start()

    def _step(self) -> None:
        if self._current and time.monotonic() - self._t0 > self._current[2]:
            self._next()
        self.update()

    def paintEvent(self, _):
        if not self._current:
            return
        title, body, dur = self._current
        el = time.monotonic() - self._t0
        a = max(0.0, min(1.0, el * 6, (dur - el) * 4))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(a)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        r.translate(0, (1 - a) * -6)
        p.setPen(QPen(QColor(255, 255, 255, 24), 1))
        p.setBrush(QColor(18, 18, 21, 240))
        p.drawRoundedRect(r, 12, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(T.ACCENT))
        p.drawRoundedRect(QRectF(r.x() + 14, r.center().y() - 3, 6, 6), 3, 3)
        p.setPen(QColor(T.TEXT))
        p.setFont(T.font(13, QFont.DemiBold))
        tr = QRectF(r.x() + 30, r.y() + (12 if body else 0), r.width() - 44, 20 if body else r.height())
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, title)
        if body:
            p.setPen(QColor(T.TEXT2))
            p.setFont(T.font(12))
            p.drawText(QRectF(r.x() + 30, r.y() + 33, r.width() - 44, 18), Qt.AlignLeft | Qt.AlignVCenter, body)
        p.end()
