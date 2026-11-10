"""Composants visuels : cartes de statistiques, étoiles animées, graphiques."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import icons
from . import theme as T


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")


class StatCard(Card):
    """Carte : icône + libellé + grande valeur, avec animation au changement."""

    def __init__(self, icon: str, label: str, accent: str = T.GOLD, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setMinimumSize(190, 104)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon, 44))
        ic.setFixedSize(48, 48)
        lay.addWidget(ic, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.label = QLabel(label.upper())
        self.label.setObjectName("muted")
        self.label.setFont(T.ui_font(8, QFont.Bold))
        self.value = QLabel("0")
        self.value.setFont(T.display_font(22))
        self.value.setStyleSheet(f"color: {accent};")
        self.sub = QLabel("")
        self.sub.setObjectName("muted")
        self.sub.setFont(T.ui_font(8))
        col.addWidget(self.label)
        col.addWidget(self.value)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self._flash = 0.0
        self._timer = QTimer(self, interval=16, timeout=self._tick)

    def set(self, value: str, sub: str = "") -> None:
        if value != self.value.text() and self.value.text() not in ("0", ""):
            self._flash = 1.0
            self._timer.start()
        self.value.setText(value)
        self.sub.setText(sub)

    def _tick(self):
        self._flash = max(0.0, self._flash - 0.03)
        if self._flash <= 0:
            self._timer.stop()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._flash > 0:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(T.c(self.accent, int(255 * self._flash)), 2))
            p.setBrush(T.c(self.accent, int(40 * self._flash)))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
            p.end()


class StarBar(QWidget):
    """5 grandes étoiles + animation lors du gain d'une étoile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stars = 0
        self.setMinimumHeight(70)
        self._anim_star = -1
        self._t0 = 0.0
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._idle = QTimer(self, interval=50, timeout=self.update)  # scintillement discret
        self._idle.start()

    def sizeHint(self) -> QSize:
        return QSize(380, 76)

    def set_stars(self, n: int, animate: bool = True) -> None:
        if animate and n > self.stars:
            self._anim_star = n - 1
            self._t0 = time.monotonic()
            self._timer.start()
        self.stars = n
        self.update()

    def _tick(self):
        if time.monotonic() - self._t0 > 1.6:
            self._anim_star = -1
            self._timer.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        size = min(h * 0.85, w / 6.2)
        gap = (w - 5 * size) / 6
        now = time.monotonic()
        for i in range(5):
            cx = gap + i * (size + gap) + size / 2
            cy = h / 2
            k, glow = 1.0, 0.0
            if i == self._anim_star:
                ph = (now - self._t0) / 1.6
                k = 1 + 0.45 * math.sin(math.pi * min(1, ph * 1.4)) if ph < 1 else 1
                glow = max(0.0, 1 - ph)
                # anneaux d'étincelles
                p.setPen(QPen(T.c(T.GOLD, int(200 * glow)), 2))
                p.setBrush(Qt.NoBrush)
                rr = size * (0.5 + ph * 1.2)
                p.drawEllipse(QPointF(cx, cy), rr, rr)
                for j in range(8):
                    a = j * math.pi / 4 + ph * 2
                    d = size * (0.4 + ph)
                    p.setPen(Qt.NoPen)
                    p.setBrush(T.c("#fde68a", int(255 * glow)))
                    p.drawEllipse(QPointF(cx + d * math.cos(a), cy + d * math.sin(a)), 3, 3)
            elif i < self.stars:
                glow = 0.25 + 0.15 * math.sin(now * 2 + i)
            s = size * k
            icons.draw_star(p, QRectF(cx - s / 2, cy - s / 2, s, s), i < self.stars, glow)
        p.end()


class GlowProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.setFixedHeight(16)

    def set_value(self, v: float) -> None:
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(32, 26, 60))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.value > 0:
            f = QRectF(r.x(), r.y(), max(r.height(), r.width() * self.value), r.height())
            g = QLinearGradient(f.topLeft(), f.topRight())
            g.setColorAt(0, QColor(T.VIOLET))
            g.setColorAt(0.6, QColor(T.BLUE))
            g.setColorAt(1, QColor(T.GOLD))
            p.setBrush(g)
            p.drawRoundedRect(f, r.height() / 2, r.height() / 2)
            p.setBrush(T.c("#ffffff", 50))
            p.drawRoundedRect(QRectF(f.x() + 2, f.y() + 1, f.width() - 4, f.height() / 2 - 1), 3, 3)
        p.end()


class _Chart(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.setMinimumHeight(220)
        self.empty_text = "Pas encore de données — jouez une partie !"

    def _frame(self, p: QPainter):
        r = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        p.setPen(QPen(QColor(T.BORDER), 1))
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(T.PANEL2))
        g.setColorAt(1, QColor(T.PANEL))
        p.setBrush(g)
        p.drawRoundedRect(r, 14, 14)
        p.setPen(QColor(T.TEXT))
        p.setFont(T.ui_font(10, QFont.Bold))
        p.drawText(QRectF(18, 10, r.width() - 36, 26), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        return QRectF(48, 46, r.width() - 66, r.height() - 82)

    def _axes(self, p: QPainter, plot: QRectF, vmax: float):
        p.setFont(T.ui_font(8))
        steps = 4
        for i in range(steps + 1):
            y = plot.bottom() - plot.height() * i / steps
            p.setPen(QPen(T.c(T.BORDER, 160), 1, Qt.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y - 8, plot.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{int(round(vmax * i / steps))}")


class BarChart(_Chart):
    def __init__(self, title: str, color: str = T.VIOLET, parent=None):
        super().__init__(title, parent)
        self.data: list[tuple[str, float]] = []
        self.color = color

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = self._frame(p)
        if not self.data:
            p.setPen(QColor(T.MUTED))
            p.drawText(plot, Qt.AlignCenter, self.empty_text)
            return
        vmax = max(4, max(v for _, v in self.data))
        vmax = math.ceil(vmax / 4) * 4
        self._axes(p, plot, vmax)
        n = len(self.data)
        bw = plot.width() / n
        label_every = max(1, n // 8)
        for i, (lab, v) in enumerate(self.data):
            h = plot.height() * v / vmax
            r = QRectF(plot.left() + i * bw + bw * 0.18, plot.bottom() - h, bw * 0.64, h)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(T.GOLD) if i == n - 1 else QColor(self.color).lighter(130))
            g.setColorAt(1, QColor(self.color).darker(160))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            path = QPainterPath()
            path.addRoundedRect(r, min(5, bw * 0.2), min(5, bw * 0.2))
            p.drawPath(path)
            if i % label_every == 0 or i == n - 1:
                p.setPen(QColor(T.MUTED))
                p.setFont(T.ui_font(7))
                p.drawText(QRectF(plot.left() + i * bw - 20, plot.bottom() + 4, bw + 40, 16), Qt.AlignCenter, lab)
        p.end()


class LineChart(_Chart):
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.points: list[tuple[float, float]] = []
        self.marks: list[float] = []  # abscisses des jetons trouvés

    def set_data(self, points, marks=()):
        self.points = list(points)
        self.marks = list(marks)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = self._frame(p)
        if len(self.points) < 2:
            p.setPen(QColor(T.MUTED))
            p.drawText(plot, Qt.AlignCenter, self.empty_text)
            return
        xs = [x for x, _ in self.points]
        x0, x1 = min(xs), max(xs)
        vmax = max(4, max(y for _, y in self.points))
        vmax = math.ceil(vmax / 4) * 4
        self._axes(p, plot, vmax)

        def pt(x, y):
            fx = 0 if x1 == x0 else (x - x0) / (x1 - x0)
            return QPointF(plot.left() + fx * plot.width(), plot.bottom() - plot.height() * y / vmax)

        path = QPainterPath(pt(*self.points[0]))
        for x, y in self.points[1:]:
            path.lineTo(pt(x, y))
        area = QPainterPath(path)
        area.lineTo(QPointF(plot.right(), plot.bottom()))
        area.lineTo(QPointF(plot.left(), plot.bottom()))
        g = QLinearGradient(plot.topLeft(), plot.bottomLeft())
        g.setColorAt(0, T.c(T.VIOLET, 140))
        g.setColorAt(1, T.c(T.BLUE, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(area)
        pen = QPen(QColor(T.VIOLET).lighter(130), 2.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        for mx in self.marks:
            if x0 <= mx <= x1:
                y = next((yy for xx, yy in self.points if xx >= mx), self.points[-1][1])
                c = pt(mx, y)
                icons.draw_token(p, QRectF(c.x() - 9, c.y() - 9, 18, 18))
        p.end()


class StatusPill(QWidget):
    COLORS = {"active": (T.GREEN, "Analyse des replays active"), "configuring": (T.ORANGE, "Configuration requise"),
              "inactive": (T.RED, "Analyse inactive")}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = "inactive"
        self.message = ""
        self.setFixedHeight(34)
        self.setMinimumWidth(220)
        QTimer(self, interval=60, timeout=self.update).start()

    def set_status(self, level: str, message: str = "") -> None:
        self.level, self.message = level, message
        self.setToolTip(message)
        self.update()

    def paintEvent(self, _):
        color, text = self.COLORS.get(self.level, self.COLORS["inactive"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(T.c(color, 160), 1))
        p.setBrush(T.c(color, 30))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 4) if self.level == "active" else 0.0
        p.setPen(Qt.NoPen)
        p.setBrush(T.c(color, int(90 * pulse)))
        p.drawEllipse(QPointF(r.x() + 17, r.center().y()), 9, 9)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(r.x() + 17, r.center().y()), 5, 5)
        p.setPen(QColor(T.TEXT))
        p.setFont(T.ui_font(9, QFont.Bold))
        p.drawText(r.adjusted(32, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.end()


def h1(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("h1")
    lab.setFont(T.display_font(20))
    return lab


def h2(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("h2")
    return lab


def muted(text: str, wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("muted")
    lab.setWordWrap(wrap)
    return lab


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, m = seconds // 3600, (seconds % 3600) // 60
    return f"{h} h {m:02d} min" if h else f"{m} min {seconds % 60:02d} s"
