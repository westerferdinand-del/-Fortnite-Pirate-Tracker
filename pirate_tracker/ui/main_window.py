"""Fenêtre principale : barre latérale + pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from . import icons
from . import theme as T
from .detection_page import DetectionPage
from .pages import DashboardPage, HistoryPage, ProgressPage
from .settings_page import SettingsPage
from .widgets import muted


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1260, 860)
        self.setMinimumSize(1020, 680)

        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(16, 20, 16, 16)
        sv.setSpacing(6)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_pixmap(44))
        brand.addWidget(logo)
        bcol = QVBoxLayout()
        bcol.setSpacing(0)
        t1 = QLabel("PIRATE")
        t1.setFont(T.display_font(15))
        t1.setStyleSheet(f"color: {T.GOLD};")
        t2 = QLabel("TRACKER")
        t2.setFont(T.display_font(11))
        t2.setStyleSheet(f"color: {T.VIOLET}; letter-spacing: 3px;")
        bcol.addWidget(t1)
        bcol.addWidget(t2)
        brand.addLayout(bcol)
        brand.addStretch(1)
        sv.addLayout(brand)
        sv.addSpacing(22)

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(ctx),
            "history": HistoryPage(ctx),
            "progress": ProgressPage(ctx),
            "detection": DetectionPage(ctx),
            "settings": SettingsPage(ctx),
        }
        nav = [("dashboard", "chest", "Tableau de bord"), ("history", "list", "Historique"),
               ("progress", "star", "Étoiles && niveaux"), ("detection", "eye", "Détection"),
               ("settings", "gear", "Paramètres")]
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.nav_buttons = {}
        for i, (key, ic, label) in enumerate(nav):
            self.stack.addWidget(self.pages[key])
            b = QPushButton("  " + label)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic, 22))
            b.setIconSize(QSize(22, 22))
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.group.addButton(b, i)
            self.nav_buttons[key] = b
            sv.addWidget(b)
        sv.addStretch(1)

        self.widget_btn = QPushButton("Masquer le widget")
        self.widget_btn.clicked.connect(ctx.toggle_overlay)
        sv.addWidget(self.widget_btn)
        foot = muted(f"v{__version__} · capture d'écran uniquement,\naucune modification du jeu", wrap=True)
        foot.setFont(T.ui_font(7))
        sv.addWidget(foot)

        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.show_page("dashboard")

    def show_page(self, key: str):
        self.nav_buttons[key].setChecked(True)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh(False) if key in ("dashboard", "progress") else page.refresh()

    def closeEvent(self, e):
        # Fermer la fenêtre ne quitte pas : le comptage continue (icône dans la barre des tâches).
        if self.ctx.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        self.ctx.tray_message("Pirate Tracker continue de compter",
                              "Le comptage reste actif. Clic droit sur l'icône pour quitter.")
