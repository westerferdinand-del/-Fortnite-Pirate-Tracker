"""Fenêtre principale v2 : barre latérale sobre + 4 pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from . import icons
from . import theme as T
from .pages import LootPage, MatchesPage, OverviewPage
from .settings_page import SettingsPage
from .widgets import StatusDot, faint

NAV = [("overview", "overview", "Vue d'ensemble"), ("matches", "matches", "Parties"), ("loot", "loot", "Butin"),
       ("settings", "settings", "Réglages")]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1280, 860)
        self.setMinimumSize(980, 640)

        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(224)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 22, 14, 18)
        sv.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(10)
        logo = QLabel()
        pm = icons.app_pixmap(56)
        pm.setDevicePixelRatio(2.0)
        logo.setPixmap(pm)
        brand.addWidget(logo)
        name = QLabel("Pirate Tracker")
        name.setFont(T.font(15, QFont.DemiBold))
        brand.addWidget(name)
        brand.addStretch(1)
        sv.addLayout(brand)
        sv.addSpacing(26)

        self.stack = QStackedWidget()
        self.pages = {
            "overview": OverviewPage(ctx),
            "matches": MatchesPage(ctx),
            "loot": LootPage(ctx),
            "settings": SettingsPage(ctx),
        }
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav_buttons = {}
        for i, (key, ic, text) in enumerate(NAV):
            self.stack.addWidget(self.pages[key])
            b = QPushButton("  " + text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic, 18))
            b.setIconSize(QSize(18, 18))
            b.setFont(T.font(13, QFont.Medium))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.group.addButton(b, i)
            self.nav_buttons[key] = b
            sv.addWidget(b)
        sv.addStretch(1)

        self.status = StatusDot()
        self.status.setContentsMargins(0, 0, 0, 0)
        st = QHBoxLayout()
        st.setContentsMargins(10, 0, 0, 0)
        st.addWidget(self.status)
        sv.addLayout(st)
        sv.addSpacing(10)
        self.widget_btn = QPushButton("Masquer le widget")
        self.widget_btn.setObjectName("nav")
        self.widget_btn.setIcon(icons.icon("chest", 18))
        self.widget_btn.setIconSize(QSize(18, 18))
        self.widget_btn.setFont(T.font(13, QFont.Medium))
        self.widget_btn.setCursor(Qt.PointingHandCursor)
        self.widget_btn.clicked.connect(ctx.toggle_overlay)
        sv.addWidget(self.widget_btn)
        sv.addSpacing(6)
        ver = faint(f"v{__version__}", wrap=False)
        ver.setFont(T.font(11))
        ver.setContentsMargins(10, 0, 0, 0)
        sv.addWidget(ver)

        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.show_page("overview")

    def show_page(self, key: str):
        self.nav_buttons[key].setChecked(True)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        page.refresh()

    def set_status(self, level: str, message: str):
        self.status.set_status(level, message)

    def closeEvent(self, e):
        # Fermer la fenêtre ne quitte pas : le comptage continue (icône près de l'horloge).
        if self.ctx.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.ctx.tray_message("Pirate Tracker continue de compter",
                              "Clic droit sur l'icône près de l'horloge pour quitter.")
