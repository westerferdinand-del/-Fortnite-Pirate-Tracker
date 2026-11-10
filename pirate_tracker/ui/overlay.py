"""Mini-widget flottant transparent, toujours au premier plan, déplaçable."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from . import icons
from . import theme as T

SIZES = {"small": 0.78, "medium": 1.0, "large": 1.32}
POSITIONS = ["top-left", "top-center", "top-right", "bottom-left", "bottom-right", "custom"]
STATUS_COLORS = {"active": T.GREEN, "configuring": T.ORANGE, "inactive": T.RED}


class OverlayWidget(QWidget):
    open_dashboard = Signal()
    settings_changed = Signal()

    BASE_W, ROW_H, HEAD_H = 300, 34, 30

    def __init__(self, config):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.config = config
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Pirate Tracker — widget")
        self.values = {"chests": 0, "last": None, "tokens": 0, "level": 1, "stars": 0, "since": 0, "progress": 0.0}
        self.status = "inactive"
        self._drag: QPoint | None = None
        self._anim = {}  # nom -> heure de début
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._pulse = QTimer(self, interval=200, timeout=self.update)  # voyant d'état
        self._pulse.start()
        self.apply_settings()

    # ------------------------------------------------------------------ settings
    @property
    def ocfg(self) -> dict:
        return self.config.section("overlay")

    @property
    def scale(self) -> float:
        return SIZES.get(self.ocfg.get("size", "medium"), 1.0)

    def _rows(self) -> list[str]:
        rows = ["chests"]
        if self.ocfg.get("show_last_match", True):
            rows.append("last")
        rows.append("tokens")
        if self.ocfg.get("show_level", True):
            rows.append("level")
        if self.ocfg.get("show_since_token", True):
            rows.append("since")
        return rows

    def apply_settings(self) -> None:
        s = self.scale
        h = self.HEAD_H + self.ROW_H * len(self._rows()) + 22
        self.setFixedSize(int(self.BASE_W * s), int(h * s))
        self.setWindowOpacity(max(0.2, min(1.0, float(self.ocfg.get("opacity", 0.85)))))
        self.move_to_position()
        self.update()

    def move_to_position(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        g = screen.geometry()
        pos = self.ocfg.get("position", "top-center")
        m = 16
        w, h = self.width(), self.height()
        pts = {
            "top-left": (g.left() + m, g.top() + m),
            "top-center": (g.center().x() - w // 2, g.top() + m),
            "top-right": (g.right() - w - m, g.top() + m + 220),  # sous la mini-carte
            "bottom-left": (g.left() + m, g.bottom() - h - 200),
            "bottom-right": (g.right() - w - m, g.bottom() - h - 160),
        }
        if pos == "custom":
            x, y = self.ocfg.get("custom_pos", [100, 40])
        else:
            x, y = pts.get(pos, pts["top-center"])
        self.move(int(x), int(y))

    # ------------------------------------------------------------------ data
    def set_values(self, chests: int, last: int | None, tokens: int, level: int, stars: int, since: int,
                   progress: float) -> None:
        """Mis à jour à la fin de chaque partie (après analyse du replay)."""
        prev = dict(self.values)
        self.values = {"chests": chests, "last": last, "tokens": tokens, "level": level, "stars": stars,
                       "since": since, "progress": progress}
        if chests > prev["chests"]:
            self.animate("chest")
        if tokens > prev["tokens"]:
            self.animate("token")
        if level > prev["level"] or (level == prev["level"] and stars > prev["stars"]):
            self.animate("star")
        self.update()

    def set_status(self, level: str) -> None:
        self.status = level
        self.update()

    def animate(self, name: str) -> None:
        self._anim[name] = time.monotonic()
        if not self._timer.isActive():
            self._timer.start()

    def _phase(self, name: str, dur: float) -> float | None:
        t0 = self._anim.get(name)
        if t0 is None:
            return None
        x = (time.monotonic() - t0) / dur
        if x >= 1:
            self._anim.pop(name, None)
            return None
        return x

    def _tick(self) -> None:
        if not self._anim:
            self._timer.stop()
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _):
        s = self.scale
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        radius = 14 * s

        glow = 0.0
        for name, dur in (("chest", 0.9), ("token", 3.0), ("star", 1.6)):
            ph = self._phase(name, dur)
            if ph is not None:
                glow = max(glow, 1 - ph)

        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, QColor(20, 12, 42, 235))
        bg.setColorAt(1, QColor(8, 10, 30, 235))
        p.setBrush(bg)
        border = QColor(T.GOLD) if glow > 0 else QColor(self.ocfg.get("accent", T.VIOLET))
        border.setAlpha(int(140 + 115 * glow))
        p.setPen(QPen(border, (1.5 + 2.5 * glow) * s))
        p.drawRoundedRect(r, radius, radius)

        # En-tête
        head = QRectF(r.x() + 12 * s, r.y() + 6 * s, r.width() - 24 * s, self.HEAD_H * s - 6 * s)
        icons.draw_token(p, QRectF(head.x(), head.y() + 2 * s, 18 * s, 18 * s))
        p.setPen(QColor(T.GOLD))
        f = T.display_font(int(9 * s))
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5 * s)
        p.setFont(f)
        p.drawText(QRectF(head.x() + 24 * s, head.y(), head.width(), 22 * s), Qt.AlignVCenter | Qt.AlignLeft,
                   "PIRATE TRACKER")
        dot = QColor(STATUS_COLORS.get(self.status, T.RED))
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 4) if self.status == "active" else 1.0
        p.setPen(Qt.NoPen)
        dot.setAlpha(int(120 + 135 * pulse))
        p.setBrush(dot)
        p.drawEllipse(QPointF(head.right() - 6 * s, head.y() + 11 * s), 5 * s, 5 * s)
        p.setPen(QPen(T.c(T.BORDER), 1))
        p.drawLine(QPointF(r.x() + 10 * s, r.y() + self.HEAD_H * s), QPointF(r.right() - 10 * s, r.y() + self.HEAD_H * s))

        y = r.y() + self.HEAD_H * s + 2 * s
        v = self.values
        labels = {
            "chests": ("chest", "COFFRES OUVERTS", f"{v['chests']:03d}"),
            "last": ("chest_open", "DERNIÈRE PARTIE", "—" if v["last"] is None else f"+{v['last']}"),
            "tokens": ("token", "JETONS TROUVÉS", f"{v['tokens']}"),
            "level": ("star", "NIVEAU", f"{v['level']}"),
            "since": ("flame", "DEPUIS LE DERNIER JETON", f"{v['since']:03d}"),
        }
        for key in self._rows():
            ic, label, val = labels[key]
            row = QRectF(r.x() + 12 * s, y, r.width() - 24 * s, self.ROW_H * s)
            icons.DRAWERS[ic](p, QRectF(row.x(), row.y() + 6 * s, 22 * s, 22 * s))
            p.setPen(QColor(T.MUTED))
            p.setFont(T.ui_font(int(7.5 * s), QFont.DemiBold))
            p.drawText(QRectF(row.x() + 30 * s, row.y(), row.width() * 0.62, row.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, label)
            if key == "level":
                for i in range(5):
                    ph = self._phase("star", 1.6) if i == v["stars"] - 1 else None
                    k = 1.0 + (0.6 * math.sin(math.pi * ph) if ph is not None else 0)
                    sz = 11 * s * k
                    cx = row.x() + 92 * s + i * 14 * s
                    icons.draw_star(p, QRectF(cx - sz / 2 + 6 * s, row.center().y() - sz / 2, sz, sz),
                                    i < v["stars"], glow=(1 - ph) if ph is not None else 0)
            pop = 0.0
            if key == "chests":
                ph = self._phase("chest", 0.9)
                pop = math.sin(math.pi * ph) if ph is not None else 0
            if key == "tokens":
                ph = self._phase("token", 3.0)
                pop = abs(math.sin(math.pi * 3 * ph)) if ph is not None else 0
            fv = T.display_font(int((14 + 4 * pop) * s))
            p.setFont(fv)
            if key == "last":
                ph = self._phase("chest", 0.9)
                pop = math.sin(math.pi * ph) if ph is not None else 0
            p.setPen(QColor("#fff3b0") if pop > 0 else QColor(T.GOLD if key not in ("since", "last") else T.TEXT))
            p.drawText(row, Qt.AlignVCenter | Qt.AlignRight, val)
            y += self.ROW_H * s

        # Barre de progression vers la prochaine étoile
        bar = QRectF(r.x() + 12 * s, r.bottom() - 13 * s, r.width() - 24 * s, 5 * s)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 32, 72))
        p.drawRoundedRect(bar, 2.5 * s, 2.5 * s)
        fill = QRectF(bar.x(), bar.y(), bar.width() * max(0.0, min(1.0, v["progress"])), bar.height())
        g = QLinearGradient(bar.topLeft(), bar.topRight())
        g.setColorAt(0, QColor(T.VIOLET))
        g.setColorAt(1, QColor(T.GOLD))
        p.setBrush(g)
        p.drawRoundedRect(fill, 2.5 * s, 2.5 * s)
        p.end()

    # ------------------------------------------------------------------ interaction
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.config.set("overlay", "position", "custom", save=False)
            self.config.set("overlay", "custom_pos", [self.x(), self.y()])
            self.settings_changed.emit()

    def mouseDoubleClickEvent(self, e):
        self.open_dashboard.emit()

    def contextMenuEvent(self, e):
        m = QMenu(self)
        size_menu = m.addMenu("Taille")
        for key, label in (("small", "Petit"), ("medium", "Moyen"), ("large", "Grand")):
            a = QAction(label, size_menu, checkable=True, checked=self.ocfg.get("size") == key)
            a.triggered.connect(lambda _=False, k=key: self._set("size", k))
            size_menu.addAction(a)
        pos_menu = m.addMenu("Position")
        names = {"top-left": "Haut gauche", "top-center": "Haut centre", "top-right": "Haut droite",
                 "bottom-left": "Bas gauche", "bottom-right": "Bas droite"}
        for key, label in names.items():
            a = QAction(label, pos_menu, checkable=True, checked=self.ocfg.get("position") == key)
            a.triggered.connect(lambda _=False, k=key: self._set("position", k))
            pos_menu.addAction(a)
        op_menu = m.addMenu("Transparence")
        for val in (1.0, 0.85, 0.7, 0.55, 0.4):
            a = QAction(f"{int(val * 100)} %", op_menu, checkable=True,
                        checked=abs(self.ocfg.get("opacity", 0.85) - val) < 0.01)
            a.triggered.connect(lambda _=False, v=val: self._set("opacity", v))
            op_menu.addAction(a)
        m.addSeparator()
        m.addAction("Ouvrir le tableau de bord", self.open_dashboard.emit)
        m.addAction("Masquer le widget", lambda: self._set("visible", False))
        m.exec(e.globalPos())

    def _set(self, key, value):
        self.config.set("overlay", key, value)
        if key == "visible":
            self.setVisible(bool(value))
        self.apply_settings()
        self.settings_changed.emit()
