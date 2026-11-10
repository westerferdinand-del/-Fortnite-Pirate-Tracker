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

    BASE_W, BASE_H = 310, 64

    def __init__(self, config):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.config = config
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Pirate Tracker — widget")
        self.chests = 0
        self.status = "inactive"
        self._drag: QPoint | None = None
        self._anim_t0: float | None = None
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

    def apply_settings(self) -> None:
        s = self.scale
        self.setFixedSize(int(self.BASE_W * s), int(self.BASE_H * s))
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
    def set_chests(self, chests: int) -> None:
        """Total de coffres ouverts, mis à jour à la fin de chaque partie (après analyse du replay)."""
        if chests > self.chests:
            self._anim_t0 = time.monotonic()
            self._timer.start()
        self.chests = chests
        self.update()

    def set_status(self, level: str) -> None:
        self.status = level
        self.update()

    def _phase(self) -> float | None:
        if self._anim_t0 is None:
            return None
        x = (time.monotonic() - self._anim_t0) / 1.2
        if x >= 1:
            self._anim_t0 = None
            return None
        return x

    def _tick(self) -> None:
        if self._anim_t0 is None:
            self._timer.stop()
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _):
        s = self.scale
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        ph = self._phase()
        glow = (1 - ph) if ph is not None else 0.0
        pop = math.sin(math.pi * ph) if ph is not None else 0.0

        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, QColor(20, 12, 42, 235))
        bg.setColorAt(1, QColor(8, 10, 30, 235))
        p.setBrush(bg)
        border = QColor(T.GOLD) if glow > 0 else QColor(self.ocfg.get("accent", T.VIOLET))
        border.setAlpha(int(150 + 105 * glow))
        p.setPen(QPen(border, (1.5 + 2.5 * glow) * s))
        p.drawRoundedRect(r, 14 * s, 14 * s)

        icon = 38 * s
        icons.draw_chest(p, QRectF(r.x() + 12 * s, r.center().y() - icon / 2 - 2 * s, icon, icon), opened=glow > 0)

        p.setPen(QColor(T.MUTED))
        f = T.ui_font(int(8 * s), QFont.Bold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0 * s)
        p.setFont(f)
        p.drawText(QRectF(r.x() + 60 * s, r.y(), r.width(), r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   "COFFRES OUVERTS")

        p.setFont(T.display_font(int((22 + 5 * pop) * s)))
        p.setPen(QColor("#fff3b0") if pop > 0 else QColor(T.GOLD))
        p.drawText(r.adjusted(0, 0, -26 * s, 0), Qt.AlignVCenter | Qt.AlignRight, f"{self.chests:03d}")

        dot = QColor(STATUS_COLORS.get(self.status, T.RED))
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 4) if self.status == "active" else 1.0
        dot.setAlpha(int(120 + 135 * pulse))
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(r.right() - 12 * s, r.center().y()), 4 * s, 4 * s)
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
