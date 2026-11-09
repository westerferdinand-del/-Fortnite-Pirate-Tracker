"""Icônes vectorielles dessinées en code (coffre, jeton pirate, étoile, flamme…)."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QRadialGradient)

from . import theme as T


def _grad(r: QRectF, a: str, b: str) -> QLinearGradient:
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    return g


def star_polygon(cx: float, cy: float, r: float, inner: float = 0.45) -> QPolygonF:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * inner
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return QPolygonF(pts)


def draw_star(p: QPainter, r: QRectF, filled: bool = True, glow: float = 0.0) -> None:
    cx, cy, rad = r.center().x(), r.center().y(), min(r.width(), r.height()) / 2
    if glow > 0:
        g = QRadialGradient(QPointF(cx, cy), rad * 1.6)
        g.setColorAt(0, T.c(T.GOLD, int(160 * glow)))
        g.setColorAt(1, T.c(T.GOLD, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), rad * 1.6, rad * 1.6)
    poly = star_polygon(cx, cy, rad * 0.95)
    if filled:
        p.setBrush(_grad(r, "#fff3b0", T.GOLD_D))
        p.setPen(QPen(QColor("#fde68a"), max(1.0, rad * 0.08)))
    else:
        p.setBrush(QColor(52, 42, 92))
        p.setPen(QPen(QColor(130, 116, 190), max(1.0, rad * 0.09)))
    p.drawPolygon(poly)


def draw_chest(p: QPainter, r: QRectF, opened: bool = False) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    body = QRectF(x + w * 0.08, y + h * 0.45, w * 0.84, h * 0.45)
    p.setPen(QPen(QColor("#3b2208"), max(1.0, w * 0.04)))
    p.setBrush(_grad(body, "#a0612b", "#5c3311"))
    p.drawRoundedRect(body, w * 0.06, w * 0.06)
    if opened:
        g = QRadialGradient(QPointF(x + w / 2, y + h * 0.42), w * 0.5)
        g.setColorAt(0, T.c("#fff7c2", 230))
        g.setColorAt(1, T.c(T.GOLD, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(x + w / 2, y + h * 0.42), w * 0.5, h * 0.35)
        lid = QPolygonF([QPointF(x + w * 0.1, y + h * 0.45), QPointF(x + w * 0.9, y + h * 0.45),
                         QPointF(x + w * 0.82, y + h * 0.12), QPointF(x + w * 0.18, y + h * 0.12)])
        p.setPen(QPen(QColor("#3b2208"), max(1.0, w * 0.04)))
        p.setBrush(_grad(QRectF(x, y, w, h * 0.45), "#c07a3a", "#6b3c15"))
        p.drawPolygon(lid)
    else:
        lid = QRectF(x + w * 0.05, y + h * 0.18, w * 0.9, h * 0.32)
        path = QPainterPath()
        path.addRoundedRect(lid, w * 0.12, w * 0.12)
        p.setBrush(_grad(lid, "#c07a3a", "#7a4519"))
        p.drawPath(path)
    # ferrures dorées
    p.setPen(Qt.NoPen)
    p.setBrush(_grad(r, "#fde68a", T.GOLD_D))
    p.drawRect(QRectF(x + w * 0.2, y + h * 0.45, w * 0.08, h * 0.45))
    p.drawRect(QRectF(x + w * 0.72, y + h * 0.45, w * 0.08, h * 0.45))
    p.drawRoundedRect(QRectF(x + w * 0.42, y + h * 0.4, w * 0.16, h * 0.2), 2, 2)


def draw_token(p: QPainter, r: QRectF) -> None:
    cx, cy = r.center().x(), r.center().y()
    rad = min(r.width(), r.height()) / 2 * 0.95
    g = QRadialGradient(QPointF(cx - rad * 0.3, cy - rad * 0.3), rad * 1.4)
    g.setColorAt(0, QColor("#c4b5fd"))
    g.setColorAt(0.5, QColor(T.VIOLET))
    g.setColorAt(1, QColor("#2e1065"))
    p.setPen(QPen(QColor(T.GOLD), max(1.5, rad * 0.14)))
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), rad, rad)
    # tête de mort
    gold = _grad(r, "#fff3b0", T.GOLD_D)
    p.setPen(Qt.NoPen)
    p.setBrush(gold)
    p.drawEllipse(QPointF(cx, cy - rad * 0.12), rad * 0.42, rad * 0.38)
    p.drawRoundedRect(QRectF(cx - rad * 0.24, cy + rad * 0.12, rad * 0.48, rad * 0.26), rad * 0.06, rad * 0.06)
    p.setBrush(QColor("#2e1065"))
    p.drawEllipse(QPointF(cx - rad * 0.16, cy - rad * 0.14), rad * 0.11, rad * 0.12)
    p.drawEllipse(QPointF(cx + rad * 0.16, cy - rad * 0.14), rad * 0.11, rad * 0.12)
    p.setPen(QPen(gold, max(1.5, rad * 0.12), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx - rad * 0.55, cy + rad * 0.62), QPointF(cx + rad * 0.55, cy + rad * 0.3))
    p.drawLine(QPointF(cx + rad * 0.55, cy + rad * 0.62), QPointF(cx - rad * 0.55, cy + rad * 0.3))


def draw_flame(p: QPainter, r: QRectF) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    path = QPainterPath(QPointF(x + w * 0.5, y + h * 0.05))
    path.cubicTo(x + w * 0.95, y + h * 0.4, x + w * 0.9, y + h * 0.95, x + w * 0.5, y + h * 0.95)
    path.cubicTo(x + w * 0.1, y + h * 0.95, x + w * 0.05, y + h * 0.55, x + w * 0.35, y + h * 0.35)
    path.cubicTo(x + w * 0.35, y + h * 0.55, x + w * 0.45, y + h * 0.6, x + w * 0.5, y + h * 0.05)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor("#fde047"))
    g.setColorAt(0.6, QColor("#f97316"))
    g.setColorAt(1, QColor("#dc2626"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    inner = QPainterPath(QPointF(x + w * 0.5, y + h * 0.5))
    inner.cubicTo(x + w * 0.72, y + h * 0.7, x + w * 0.68, y + h * 0.9, x + w * 0.5, y + h * 0.9)
    inner.cubicTo(x + w * 0.32, y + h * 0.9, x + w * 0.3, y + h * 0.7, x + w * 0.5, y + h * 0.5)
    p.setBrush(QColor("#fef9c3"))
    p.drawPath(inner)


def draw_clock(p: QPainter, r: QRectF) -> None:
    cx, cy, rad = r.center().x(), r.center().y(), min(r.width(), r.height()) / 2 * 0.85
    p.setPen(QPen(QColor(T.CYAN), rad * 0.18))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), rad, rad)
    p.setPen(QPen(QColor(T.TEXT), rad * 0.16, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx, cy), QPointF(cx, cy - rad * 0.6))
    p.drawLine(QPointF(cx, cy), QPointF(cx + rad * 0.45, cy + rad * 0.2))


def draw_trophy(p: QPainter, r: QRectF) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    gold = _grad(r, "#fff3b0", T.GOLD_D)
    p.setPen(QPen(QColor(T.GOLD), w * 0.07))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(x + w * 0.05, y + h * 0.15, w * 0.3, h * 0.35), 90 * 16, 180 * 16)
    p.drawArc(QRectF(x + w * 0.65, y + h * 0.15, w * 0.3, h * 0.35), -90 * 16, 180 * 16)
    p.setPen(Qt.NoPen)
    p.setBrush(gold)
    cup = QPainterPath(QPointF(x + w * 0.22, y + h * 0.1))
    cup.lineTo(x + w * 0.78, y + h * 0.1)
    cup.cubicTo(x + w * 0.78, y + h * 0.55, x + w * 0.6, y + h * 0.62, x + w * 0.5, y + h * 0.62)
    cup.cubicTo(x + w * 0.4, y + h * 0.62, x + w * 0.22, y + h * 0.55, x + w * 0.22, y + h * 0.1)
    p.drawPath(cup)
    p.drawRect(QRectF(x + w * 0.45, y + h * 0.6, w * 0.1, h * 0.18))
    p.drawRoundedRect(QRectF(x + w * 0.28, y + h * 0.78, w * 0.44, h * 0.12), 2, 2)


def draw_calendar(p: QPainter, r: QRectF) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    body = QRectF(x + w * 0.1, y + h * 0.18, w * 0.8, h * 0.72)
    p.setPen(QPen(QColor(T.BLUE), w * 0.07))
    p.setBrush(T.c(T.BLUE, 40))
    p.drawRoundedRect(body, w * 0.1, w * 0.1)
    p.setBrush(QColor(T.BLUE))
    p.drawRect(QRectF(x + w * 0.1, y + h * 0.18, w * 0.8, h * 0.18))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(T.TEXT))
    for i in range(3):
        for j in range(2):
            p.drawRect(QRectF(x + w * (0.22 + i * 0.22), y + h * (0.48 + j * 0.2), w * 0.12, h * 0.1))


def draw_gamepad(p: QPainter, r: QRectF) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p.setPen(Qt.NoPen)
    p.setBrush(_grad(r, "#a78bfa", T.VIOLET_D))
    p.drawRoundedRect(QRectF(x + w * 0.05, y + h * 0.28, w * 0.9, h * 0.48), h * 0.24, h * 0.24)
    p.setBrush(QColor(T.TEXT))
    p.drawRect(QRectF(x + w * 0.2, y + h * 0.47, w * 0.2, h * 0.08))
    p.drawRect(QRectF(x + w * 0.26, y + h * 0.4, w * 0.08, h * 0.22))
    p.setBrush(QColor(T.GOLD))
    p.drawEllipse(QPointF(x + w * 0.68, y + h * 0.45), w * 0.05, w * 0.05)
    p.drawEllipse(QPointF(x + w * 0.78, y + h * 0.56), w * 0.05, w * 0.05)


def draw_eye(p: QPainter, r: QRectF) -> None:
    cx, cy, w, h = r.center().x(), r.center().y(), r.width(), r.height()
    path = QPainterPath(QPointF(r.x() + w * 0.05, cy))
    path.quadTo(cx, r.y() - h * 0.1, r.right() - w * 0.05, cy)
    path.quadTo(cx, r.bottom() + h * 0.1, r.x() + w * 0.05, cy)
    p.setPen(QPen(QColor(T.CYAN), w * 0.07))
    p.setBrush(T.c(T.CYAN, 30))
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(T.CYAN))
    p.drawEllipse(QPointF(cx, cy), w * 0.16, w * 0.16)


def draw_gear(p: QPainter, r: QRectF) -> None:
    cx, cy, rad = r.center().x(), r.center().y(), min(r.width(), r.height()) / 2 * 0.9
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(T.MUTED))
    for i in range(8):
        p.save()
        p.translate(cx, cy)
        p.rotate(i * 45)
        p.drawRoundedRect(QRectF(-rad * 0.15, -rad, rad * 0.3, rad * 0.4), 2, 2)
        p.restore()
    p.drawEllipse(QPointF(cx, cy), rad * 0.72, rad * 0.72)
    p.setBrush(QColor(T.BG2))
    p.drawEllipse(QPointF(cx, cy), rad * 0.3, rad * 0.3)


def draw_list(p: QPainter, r: QRectF) -> None:
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p.setPen(Qt.NoPen)
    for i in range(3):
        p.setBrush(QColor(T.GOLD))
        p.drawEllipse(QPointF(x + w * 0.18, y + h * (0.25 + i * 0.25)), w * 0.07, w * 0.07)
        p.setBrush(QColor(T.TEXT))
        p.drawRoundedRect(QRectF(x + w * 0.35, y + h * (0.21 + i * 0.25), w * 0.55, h * 0.09), 2, 2)


DRAWERS = {
    "chest": draw_chest,
    "chest_open": lambda p, r: draw_chest(p, r, True),
    "token": draw_token,
    "star": draw_star,
    "star_empty": lambda p, r: draw_star(p, r, False),
    "flame": draw_flame,
    "clock": draw_clock,
    "trophy": draw_trophy,
    "calendar": draw_calendar,
    "gamepad": draw_gamepad,
    "eye": draw_eye,
    "gear": draw_gear,
    "list": draw_list,
}


@lru_cache(maxsize=256)
def pixmap(name: str, size: int = 32) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    DRAWERS[name](p, QRectF(1, 1, size - 2, size - 2))
    p.end()
    return pm


def icon(name: str, size: int = 32) -> QIcon:
    return QIcon(pixmap(name, size))


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(s))
    return ic


def app_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, size, size)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#2e1065"))
    g.setColorAt(1, QColor("#0b1440"))
    p.setPen(QPen(QColor(T.GOLD), max(1.0, size * 0.04)))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(r.adjusted(size * 0.03, size * 0.03, -size * 0.03, -size * 0.03), size * 0.22, size * 0.22)
    draw_chest(p, QRectF(size * 0.12, size * 0.22, size * 0.62, size * 0.62), True)
    draw_token(p, QRectF(size * 0.52, size * 0.08, size * 0.4, size * 0.4))
    p.end()
    return pm
