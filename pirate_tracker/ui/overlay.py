"""Widget en jeu v2 : capsule discrète affichant le total de coffres, toujours au premier plan, déplaçable."""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from . import icons
from . import theme as T

SIZES = {"small": 0.78, "medium": 1.0, "large": 1.32}
POSITIONS = ["top-left", "top-center", "top-right", "bottom-left", "bottom-right", "custom"]
STATUS_COLORS = {"active": T.GREEN, "configuring": T.ORANGE, "inactive": T.RED}


class OverlayWidget(QWidget):
    open_dashboard = Signal()
    settings_changed = Signal()

    BASE_W, BASE_H = 236, 44

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
        x = (time.monotonic() - self._anim_t0) / 2.5
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
        """Capsule sombre : icône de coffre au trait, libellé discret, nombre."""
        s = self.scale
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        ph = self._phase()
        flash = (1 - ph) if ph is not None else 0.0

        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.setBrush(QColor(11, 11, 13, 225))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        h = r.height()
        icons.draw(p, "chest", QRectF(r.x() + h * 0.36, r.center().y() - h * 0.21, h * 0.42, h * 0.42),
                   T.ACCENT, 1.8)
        p.setPen(QColor(T.MUTED))
        p.setFont(T.font(10.5 * s, QFont.DemiBold))
        p.drawText(QRectF(r.x() + h * 0.95, r.y(), r.width(), h), Qt.AlignVCenter | Qt.AlignLeft, "COFFRES")

        col = QColor(T.TEXT)
        if flash > 0:  # le nombre passe brièvement à la couleur d'accent quand il augmente
            a, b = QColor(T.ACCENT), QColor(T.TEXT)
            col = QColor(int(b.red() + (a.red() - b.red()) * flash), int(b.green() + (a.green() - b.green()) * flash),
                         int(b.blue() + (a.blue() - b.blue()) * flash))
        p.setPen(col)
        p.setFont(T.font(20 * s, QFont.DemiBold, display=True, tabular=True))
        p.drawText(r.adjusted(0, 0, -h * 0.62, 0), Qt.AlignVCenter | Qt.AlignRight,
                   f"{self.chests:,}".replace(",", "\u202f"))

        dot = QColor(STATUS_COLORS.get(self.status, T.RED))
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(r.right() - h * 0.36, r.center().y()), 2.6 * s, 2.6 * s)
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
