"""Icônes v2 : traits fins (1,6 px à 24 px), dessinées en code, une seule couleur."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme as T


def _pen(color: str, scale: float, width: float = 1.6) -> QPen:
    p = QPen(QColor(color), width * scale)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


# Chaque fonction dessine dans un repère 24×24 (mis à l'échelle par l'appelant).
def _grid(p: QPainter):
    for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)


def _list(p: QPainter):
    for y in (6, 12, 18):
        p.drawLine(QPointF(9, y), QPointF(20, y))
        p.drawPoint(QPointF(4.5, y))


def _chest(p: QPainter):
    path = QPainterPath(QPointF(3.5, 11))
    path.lineTo(3.5, 8.5)
    path.cubicTo(3.5, 6, 5.5, 4.5, 8, 4.5)
    path.lineTo(16, 4.5)
    path.cubicTo(18.5, 4.5, 20.5, 6, 20.5, 8.5)
    path.lineTo(20.5, 11)
    p.drawPath(path)
    p.drawRoundedRect(QRectF(3.5, 11, 17, 8.5), 1.5, 1.5)
    p.drawLine(QPointF(3.5, 11), QPointF(20.5, 11))
    p.drawRoundedRect(QRectF(10.5, 9.5, 3, 4), 0.8, 0.8)


def _gem(p: QPainter):
    path = QPainterPath(QPointF(6, 4.5))
    path.lineTo(18, 4.5)
    path.lineTo(21, 9.5)
    path.lineTo(12, 20)
    path.lineTo(3, 9.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(3, 9.5), QPointF(21, 9.5))
    p.drawLine(QPointF(9.5, 9.5), QPointF(12, 20))
    p.drawLine(QPointF(14.5, 9.5), QPointF(12, 20))


def _sliders(p: QPainter):
    for y, x in ((6, 15), (12, 8), (18, 13)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.save()
        p.setBrush(QColor(T.BG))
        p.drawEllipse(QPointF(x, y), 2.2, 2.2)
        p.restore()


def _replay(p: QPainter):
    path = QPainterPath()
    path.arcMoveTo(QRectF(4, 4, 16, 16), 120)
    path.arcTo(QRectF(4, 4, 16, 16), 120, 300)
    p.drawPath(path)
    p.drawLine(QPointF(5.5, 6), QPointF(8, 6.8))
    p.drawLine(QPointF(5.5, 6), QPointF(5.8, 9))
    tri = QPainterPath(QPointF(10.5, 9))
    tri.lineTo(15, 12)
    tri.lineTo(10.5, 15)
    tri.closeSubpath()
    p.drawPath(tri)


def _star(p: QPainter):
    import math

    path = QPainterPath()
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = 8.5 if i % 2 == 0 else 3.8
        pt = QPointF(12 + r * math.cos(a), 12.5 + r * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def _folder(p: QPainter):
    path = QPainterPath(QPointF(3.5, 7))
    path.lineTo(3.5, 18)
    path.quadTo(3.5, 19.5, 5, 19.5)
    path.lineTo(19, 19.5)
    path.quadTo(20.5, 19.5, 20.5, 18)
    path.lineTo(20.5, 9.5)
    path.quadTo(20.5, 8, 19, 8)
    path.lineTo(12, 8)
    path.lineTo(10, 5.5)
    path.lineTo(5, 5.5)
    path.quadTo(3.5, 5.5, 3.5, 7)
    p.drawPath(path)


def _download(p: QPainter):
    p.drawLine(QPointF(12, 4), QPointF(12, 15))
    p.drawLine(QPointF(7.5, 10.5), QPointF(12, 15))
    p.drawLine(QPointF(16.5, 10.5), QPointF(12, 15))
    p.drawLine(QPointF(4.5, 19.5), QPointF(19.5, 19.5))


def _clock(p: QPainter):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawLine(QPointF(12, 7.5), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(15, 14))


def _check(p: QPainter):
    p.drawLine(QPointF(5, 12.5), QPointF(10, 17))
    p.drawLine(QPointF(10, 17), QPointF(19, 7))


def _alert(p: QPainter):
    path = QPainterPath(QPointF(12, 4))
    path.lineTo(21, 19.5)
    path.lineTo(3, 19.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(12, 10), QPointF(12, 14))
    p.drawPoint(QPointF(12, 17))


def _coin(p: QPainter):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawEllipse(QPointF(12, 12), 5, 5)


DRAWERS = {
    "overview": _grid, "matches": _list, "chest": _chest, "loot": _gem, "settings": _sliders,
    "replay": _replay, "star": _star, "folder": _folder, "download": _download, "clock": _clock,
    "check": _check, "alert": _alert, "coin": _coin,
}


def draw(p: QPainter, name: str, rect: QRectF, color: str = T.TEXT2, width: float = 1.6) -> None:
    """Dessine l'icône ``name`` dans ``rect`` (sans fond)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.x(), rect.y())
    s = min(rect.width(), rect.height()) / 24.0
    p.scale(s, s)
    p.setPen(_pen(color, 1.0, width))
    p.setBrush(Qt.NoBrush)
    DRAWERS[name](p)
    p.restore()


@lru_cache(maxsize=256)
def pixmap(name: str, size: int = 18, color: str = T.TEXT2) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    draw(p, name, QRectF(0, 0, size, size), color)
    p.end()
    return pm


def icon(name: str, size: int = 18, color: str = T.TEXT2, active: str = T.TEXT) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, color), QIcon.Normal, QIcon.Off)
    ic.addPixmap(pixmap(name, size, active), QIcon.Normal, QIcon.On)
    ic.addPixmap(pixmap(name, size, active), QIcon.Active, QIcon.Off)
    return ic


def app_pixmap(size: int) -> QPixmap:
    """Icône de l'application : carré noir arrondi, coffre au trait doré."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    p.setPen(QPen(QColor(T.BORDER2), max(1.0, size * 0.02)))
    p.setBrush(QColor("#141417"))
    p.drawRoundedRect(r, size * 0.22, size * 0.22)
    m = size * 0.2
    draw(p, "chest", QRectF(m, m, size - 2 * m, size - 2 * m), T.ACCENT, 1.9 if size >= 32 else 2.2)
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(s))
    return ic
