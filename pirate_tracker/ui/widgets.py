"""Composants v2 : cartes plates, chiffres clés, progression par paliers, graphiques sobres."""
from __future__ import annotations

import math
import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme as T


# ---------------------------------------------------------------- texte
def label(text: str = "", obj: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if obj:
        lab.setObjectName(obj)
    lab.setWordWrap(wrap)
    return lab


def title(text: str) -> QLabel:
    lab = label(text, "title")
    lab.setFont(T.font(22, QFont.DemiBold, display=True))
    return lab


def section(text: str) -> QLabel:
    lab = label(text, "section")
    lab.setFont(T.font(15, QFont.DemiBold))
    return lab


def muted(text: str, wrap: bool = True) -> QLabel:
    return label(text, "muted", wrap)


def faint(text: str, wrap: bool = True) -> QLabel:
    return label(text, "faint", wrap)


def caps(text: str) -> QLabel:
    lab = label(text.upper(), "caps")
    f = T.font(11, QFont.DemiBold)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
    lab.setFont(f)
    return lab


# Anciens noms
h1, h2 = title, section


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hline")
    return f


def vline() -> QFrame:
    f = QFrame()
    f.setObjectName("vline")
    return f


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, m = seconds // 3600, (seconds % 3600) // 60
    return f"{h} h {m:02d}" if h else f"{m} min"


def fmt_int(n: int | float) -> str:
    """1234 → « 1 234 » (espace fine insécable)."""
    return f"{int(n):,}".replace(",", " ")


def fmt_date(ts: float, with_time: bool = True) -> str:
    d = datetime.fromtimestamp(ts)
    today = datetime.now().date()
    if d.date() == today:
        day = "Aujourd'hui"
    elif (today - d.date()).days == 1:
        day = "Hier"
    else:
        mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        day = f"{d.day} {mois[d.month - 1]}"
    return f"{day}, {d:%H:%M}" if with_time else day


# ---------------------------------------------------------------- conteneurs
class Card(QFrame):
    def __init__(self, parent=None, padding: int = 20):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(padding, padding, padding, padding)
        self.lay.setSpacing(12)


class Metric(QWidget):
    """Libellé discret + grand chiffre + précision."""

    def __init__(self, caption: str, parent=None, accent: bool = False, big: int = 26):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(caps(caption))
        self.value = QLabel("—")
        self.value.setFont(T.font(big, QFont.DemiBold, display=True, tabular=True))
        if accent:
            self.value.setStyleSheet(f"color: {T.ACCENT};")
        self.sub = faint("", wrap=False)
        self.sub.setFont(T.font(12))
        lay.addWidget(self.value)
        lay.addWidget(self.sub)

    def set(self, value: str, sub: str = "") -> None:
        self.value.setText(value)
        self.sub.setText(sub)


class MetricStrip(Card):
    """Rangée de chiffres clés séparés par de fines lignes verticales."""

    def __init__(self, captions: list[str], parent=None):
        super().__init__(parent, padding=0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.metrics: list[Metric] = []
        for i, cap in enumerate(captions):
            if i:
                row.addWidget(vline())
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(20, 18, 20, 18)
            m = Metric(cap, big=22)
            bl.addWidget(m)
            row.addWidget(box, 1)
            self.metrics.append(m)
        self.lay.addLayout(row)


class SettingRow(QWidget):
    """Ligne de réglage : titre + explication à gauche, contrôle à droite."""

    def __init__(self, title_text: str, desc: str = "", control: QWidget | None = None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 12)
        lay.setSpacing(24)
        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title_text)
        t.setFont(T.font(13, QFont.Medium))
        col.addWidget(t)
        if desc:
            d = faint(desc)
            d.setFont(T.font(12))
            col.addWidget(d)
        lay.addLayout(col, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignVCenter | Qt.AlignRight)


class Toggle(QAbstractButton):
    """Interrupteur (piste + pastille), animé."""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(36, 20)
        self._pos = 1.0 if checked else 0.0
        self._anim = QTimer(self, interval=12, timeout=self._step)
        self.toggled.connect(lambda _: self._anim.start())

    def _step(self):
        target = 1.0 if self.isChecked() else 0.0
        self._pos += (target - self._pos) * 0.35
        if abs(target - self._pos) < 0.02:
            self._pos = target
            self._anim.stop()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = QColor(T.ACCENT)
        off = QColor(T.BORDER2)
        k = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                       int(off.blue() + (on.blue() - off.blue()) * k))
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
        p.setBrush(QColor("#ffffff") if k > 0.5 else QColor(T.TEXT2))
        p.drawEllipse(QPointF(10 + 16 * k, 10), 7, 7)
        p.end()


class QRCode(QWidget):
    """QR code (module qrcode, matrice dessinée en noir sur blanc pour rester lisible par l'appareil photo)."""

    def __init__(self, size: int = 168, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._matrix: list[list[bool]] = []

    def set_text(self, text: str) -> None:
        try:
            import qrcode

            q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            q.add_data(text)
            q.make(fit=True)
            self._matrix = q.get_matrix()
        except Exception:  # noqa: BLE001 - sans QR code, l'adresse reste affichée en texte
            self._matrix = []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        if self._matrix:
            n = len(self._matrix)
            cell = (self.width() - 8) / n
            p.setBrush(QColor("#000000"))
            for y, row in enumerate(self._matrix):
                for x, on in enumerate(row):
                    if on:
                        p.drawRect(QRectF(4 + x * cell, 4 + y * cell, cell + 0.5, cell + 0.5))
        p.end()


# ---------------------------------------------------------------- progression
class StepProgress(QWidget):
    """5 segments (paliers) : segments pleins, segment en cours partiellement rempli."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps, self.done, self.partial = 5, 0, 0.0
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, done: int, partial: float) -> None:
        self.done, self.partial = done, max(0.0, min(1.0, partial))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        gap = 6
        w = (self.width() - gap * (self.steps - 1)) / self.steps
        h = self.height()
        for i in range(self.steps):
            r = QRectF(i * (w + gap), 0, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.BORDER2))
            p.drawRoundedRect(r, h / 2, h / 2)
            fill = 1.0 if i < self.done else (self.partial if i == self.done else 0.0)
            if fill > 0:
                p.setBrush(QColor(T.ACCENT))
                p.drawRoundedRect(QRectF(r.x(), 0, max(h, r.width() * fill), h), h / 2, h / 2)
        p.end()


# ---------------------------------------------------------------- graphiques
class BarChart(QWidget):
    """Barres fines, une couleur, valeur mise en avant au survol."""

    def __init__(self, parent=None, height: int = 180):
        super().__init__(parent)
        self.data: list[tuple[str, float]] = []
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self._hover = -1
        self.empty_text = "Les données apparaîtront après votre première partie."

    def set_data(self, data: list[tuple[str, float]]) -> None:
        self.data = data
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(0, 8, self.width(), self.height() - 30)

    def mouseMoveEvent(self, e):
        if self.data:
            plot = self._plot()
            i = int((e.position().x() - plot.left()) / (plot.width() / len(self.data)))
            self._hover = i if 0 <= i < len(self.data) else -1
            self.update()

    def leaveEvent(self, _):
        self._hover = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = self._plot()
        if not self.data or not any(v for _, v in self.data):
            p.setPen(QColor(T.MUTED))
            p.setFont(T.font(12))
            p.drawText(plot, Qt.AlignCenter, self.empty_text)
            return
        vmax = max(v for _, v in self.data) or 1
        n = len(self.data)
        bw = plot.width() / n
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.drawLine(QPointF(plot.left(), plot.bottom() + 0.5), QPointF(plot.right(), plot.bottom() + 0.5))
        p.setFont(T.font(11))
        step = max(1, math.ceil(n / 7))
        labelled = {n - 1 - k * step for k in range(n // step + 1)}  # depuis la fin : la dernière date est lisible
        for i, (lab, v) in enumerate(self.data):
            h = (plot.height() - 18) * v / vmax
            bar = QRectF(plot.left() + i * bw + bw * 0.22, plot.bottom() - h, bw * 0.56, h)
            p.setPen(Qt.NoPen)
            hot = i == self._hover or (self._hover < 0 and i == n - 1)
            p.setBrush(QColor(T.ACCENT if hot else "#3a3a44"))
            if h > 0:
                p.drawRoundedRect(bar, min(3, bar.width() / 2), min(3, bar.width() / 2))
            if hot and v:
                p.setPen(QColor(T.TEXT))
                p.drawText(QRectF(bar.center().x() - 30, bar.top() - 18, 60, 16), Qt.AlignCenter, fmt_int(v))
            if i in labelled:
                p.setPen(QColor(T.MUTED))
                p.drawText(QRectF(plot.left() + i * bw - 20, plot.bottom() + 6, bw + 40, 16), Qt.AlignCenter, lab)
        p.end()


# ---------------------------------------------------------------- état
class StatusDot(QWidget):
    COLORS = {"active": T.GREEN, "configuring": T.ORANGE, "inactive": T.RED}
    TEXT = {"active": "Analyse active", "configuring": "Configuration requise", "inactive": "Analyse inactive"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level, self.message = "inactive", ""
        self.setFixedHeight(22)
        self.setMinimumWidth(150)
        self._t0 = time.monotonic()
        QTimer(self, interval=80, timeout=self.update).start()

    def sizeHint(self) -> QSize:
        return QSize(180, 22)

    def set_status(self, level: str, message: str = "") -> None:
        self.level, self.message = level, message
        self.setToolTip(message)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(self.COLORS.get(self.level, T.RED))
        cy = self.height() / 2
        if self.level == "active":
            k = (time.monotonic() - self._t0) % 2.0 / 2.0
            halo = QColor(col)
            halo.setAlphaF(0.35 * (1 - k))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(5, cy), 3 + 4 * k, 3 + 4 * k)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(5, cy), 3, 3)
        p.setPen(QColor(T.TEXT2))
        p.setFont(T.font(12, QFont.Medium))
        p.drawText(QRectF(16, 0, self.width() - 16, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   self.TEXT.get(self.level, ""))
        p.end()


# Ancien nom
StatusPill = StatusDot


# ---------------------------------------------------------------- v3
class LiveChip(QWidget):
    """« Partie en cours » (point qui pulse) ou « Prêt »."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.live = False
        self.setFixedHeight(26)
        self.setMinimumWidth(150)
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=60, timeout=self.update)
        self._timer.start()

    def set_live(self, live: bool) -> None:
        self.live = live
        self.setToolTip("Fortnite enregistre la partie : le compteur sera mis à jour dès la fin de la partie."
                        if live else "En attente de la prochaine partie.")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = "Partie en cours" if self.live else "Prêt"
        f = T.font(12, QFont.Medium)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text) + 34
        r = QRectF(self.width() - w, 0, w, self.height())
        p.setPen(QPen(QColor(T.BORDER2), 1))
        p.setBrush(QColor(T.SURFACE))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), r.height() / 2, r.height() / 2)
        col = QColor(T.GREEN if self.live else T.MUTED)
        c = QPointF(r.x() + 14, r.center().y())
        if self.live:
            k = (time.monotonic() - self._t0) % 1.6 / 1.6
            halo = QColor(col)
            halo.setAlphaF(0.4 * (1 - k))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, 3 + 5 * k, 3 + 5 * k)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(c, 3.2, 3.2)
        p.setPen(QColor(T.TEXT if self.live else T.TEXT2))
        p.drawText(r.adjusted(24, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        p.end()


class MatchTimeline(QWidget):
    """Frise d'une partie : chaque coffre à l'instant où il a été ouvert, rouvert ou cassé."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.events: list[dict] = []
        self.setMinimumHeight(64)
        self.setMouseTracking(True)
        self._hover: int = -1

    def set_data(self, duration: float, events: list[dict]) -> None:
        self.duration = max(duration, max((e["t"] for e in events), default=0) + 5)
        self.events = events
        self._hover = -1
        self.update()

    def _x(self, t: float) -> float:
        return 12 + (self.width() - 24) * (t / self.duration if self.duration else 0)

    def mouseMoveEvent(self, e):
        best, bd = -1, 10.0
        for i, ev in enumerate(self.events):
            d = abs(self._x(ev["t"]) - e.position().x())
            if d < bd:
                best, bd = i, d
        if best != self._hover:
            self._hover = best
            if best >= 0:
                ev = self.events[best]
                kind = "cassé" if ev["how"] == "cassé" else ("rouvert" if ev["reopen"] else "ouvert")
                self.setToolTip(f"{int(ev['t'] // 60):02d}:{int(ev['t'] % 60):02d} · coffre {kind}")
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, _):
        self._hover = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = 24.0
        p.setPen(QPen(QColor(T.BORDER2), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(12, y), QPointF(self.width() - 12, y))
        p.setFont(T.font(11))
        step = 300 if self.duration <= 1800 else 600
        for t in range(0, int(self.duration) + 1, step):
            x = self._x(t)
            p.setPen(QPen(QColor(T.BORDER2), 1))
            p.drawLine(QPointF(x, y + 6), QPointF(x, y + 10))
            p.setPen(QColor(T.MUTED))
            if t == 0:
                p.drawText(QRectF(x - 2, y + 12, 60, 16), Qt.AlignLeft | Qt.AlignVCenter, "0 min")
            else:
                p.drawText(QRectF(x - 30, y + 12, 60, 16), Qt.AlignCenter, f"{t // 60} min")
        for i, ev in enumerate(self.events):
            x = self._x(ev["t"])
            hot = i == self._hover
            r = 6.5 if hot else 5.0
            if ev["how"] == "cassé":
                p.setPen(QPen(QColor(T.ORANGE), 2))
                p.setBrush(QColor(T.SURFACE))
                p.save()
                p.translate(x, y)
                p.rotate(45)
                p.drawRect(QRectF(-r * 0.8, -r * 0.8, r * 1.6, r * 1.6))
                p.restore()
            elif ev["reopen"]:
                p.setPen(QPen(QColor(T.ACCENT), 2))
                p.setBrush(QColor(T.SURFACE))
                p.drawEllipse(QPointF(x, y), r, r)
            else:
                p.setPen(QPen(QColor(T.SURFACE), 2))
                p.setBrush(QColor(T.ACCENT))
                p.drawEllipse(QPointF(x, y), r, r)
        if not self.events:
            p.setPen(QColor(T.MUTED))
            p.setFont(T.font(12))
            p.drawText(QRectF(0, 0, self.width(), 18), Qt.AlignCenter, "Aucun coffre dans cette partie")
        p.end()


def animate_number(label: QLabel, new_value: int, fmt=None, duration_ms: int = 900) -> None:
    """Fait défiler le nombre affiché jusqu'à sa nouvelle valeur (effet discret quand le total augmente)."""
    from PySide6.QtCore import QEasingCurve, QVariantAnimation

    fmt = fmt or fmt_int
    old = label.property("value")
    label.setProperty("value", new_value)
    if old is None or old == new_value or not label.isVisible():
        label.setText(fmt(new_value))
        return
    anim = QVariantAnimation(label)
    anim.setStartValue(int(old))
    anim.setEndValue(int(new_value))
    anim.setDuration(duration_ms)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.valueChanged.connect(lambda v: label.setText(fmt(int(v))))
    anim.start(QVariantAnimation.DeleteWhenStopped)
