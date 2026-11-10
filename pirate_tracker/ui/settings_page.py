"""Page Paramètres."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget)

from ..paths import data_dir
from .pages import scroll_page
from .widgets import h1, muted


def _slider(lo, hi, val):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(val)
    return s


class SettingsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        cfg = ctx.config
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(10)
        lay.addWidget(h1("PARAMÈTRES"))

        # --- Replays
        g = QGroupBox("Analyse des replays")
        f = QFormLayout(g)
        f.setLabelAlignment(Qt.AlignLeft)
        f.setVerticalSpacing(12)
        r = cfg.section("replays")
        f.addRow("Analyser automatiquement chaque partie",
                 self._check(r.get("enabled", True), lambda v: self._set_replays("enabled", v)))
        self.dir_lbl = muted(r.get("demos_dir") or f"Par défaut ({ctx.default_demos_dir()})", wrap=True)
        row = QHBoxLayout()
        row.addWidget(self.dir_lbl, 1)
        b = QPushButton("Changer…")
        b.clicked.connect(self._choose_dir)
        row.addWidget(b)
        b = QPushButton("Par défaut")
        b.clicked.connect(lambda: (self._set_replays("demos_dir", ""),
                                   self.dir_lbl.setText(f"Par défaut ({ctx.default_demos_dir()})")))
        row.addWidget(b)
        f.addRow("Dossier des replays", row)
        lay.addWidget(g)

        # --- Widget
        g = QGroupBox("Widget flottant")
        f = QFormLayout(g)
        f.setVerticalSpacing(12)
        o = cfg.section("overlay")
        f.addRow("Afficher le widget", self._check(o.get("visible", True), lambda v: self._set_ov("visible", v)))
        self.size = QComboBox()
        for k, lbl in (("small", "Petit"), ("medium", "Moyen"), ("large", "Grand")):
            self.size.addItem(lbl, k)
        self.size.setCurrentIndex(max(0, self.size.findData(o.get("size", "medium"))))
        self.size.currentIndexChanged.connect(lambda _: self._set_ov("size", self.size.currentData()))
        f.addRow("Taille", self.size)
        self.pos = QComboBox()
        for k, lbl in (("top-left", "Haut gauche"), ("top-center", "Haut centre"), ("top-right", "Haut droite"),
                       ("bottom-left", "Bas gauche"), ("bottom-right", "Bas droite"), ("custom", "Personnalisée (glisser)")):
            self.pos.addItem(lbl, k)
        self.pos.setCurrentIndex(max(0, self.pos.findData(o.get("position", "top-center"))))
        self.pos.currentIndexChanged.connect(lambda _: self._set_ov("position", self.pos.currentData()))
        f.addRow("Position", self.pos)
        self.op = _slider(20, 100, int(float(o.get("opacity", 0.85)) * 100))
        self.op_lbl = QLabel(f"{self.op.value()} %")
        self.op.valueChanged.connect(lambda v: (self.op_lbl.setText(f"{v} %"), self._set_ov("opacity", v / 100)))
        row = QHBoxLayout()
        row.addWidget(self.op, 1)
        row.addWidget(self.op_lbl)
        f.addRow("Opacité", row)
        self.accent = QComboBox()
        for hexv, lbl in (("#8b5cf6", "Violet"), ("#3b82f6", "Bleu"), ("#fbbf24", "Or"), ("#22d3ee", "Cyan")):
            self.accent.addItem(lbl, hexv)
        self.accent.setCurrentIndex(max(0, self.accent.findData(o.get("accent", "#8b5cf6"))))
        self.accent.currentIndexChanged.connect(lambda _: self._set_ov("accent", self.accent.currentData()))
        f.addRow("Couleur de bordure", self.accent)
        lay.addWidget(muted("Astuce : clic droit sur le widget pour changer taille/position, double-clic pour ouvrir "
                            "le tableau de bord, glisser pour le déplacer."))
        lay.addWidget(g)

        # --- Notifications & sons
        g = QGroupBox("Notifications et sons")
        f = QFormLayout(g)
        f.setVerticalSpacing(12)
        n = cfg.section("notifications")
        f.addRow("Notifications", self._check(n.get("enabled", True), lambda v: cfg.set("notifications", "enabled", v)))
        for key, lbl in (("on_match", "… à la fin de chaque partie analysée"), ("on_token", "… quand un jeton est trouvé"),
                         ("on_level", "… à chaque nouvelle étoile / niveau"), ("on_record", "… quand je bats mon record")):
            f.addRow(lbl, self._check(n.get(key, True), lambda v, k=key: cfg.set("notifications", k, v)))
        s = cfg.section("sound")
        f.addRow("Sons", self._check(s.get("enabled", True), lambda v: cfg.set("sound", "enabled", v)))
        self.vol = _slider(0, 100, int(float(s.get("volume", 0.7)) * 100))
        self.vol.valueChanged.connect(lambda v: cfg.set("sound", "volume", v / 100))
        f.addRow("Volume", self.vol)
        for key, lbl in (("match", "Son de fin de partie"), ("token", "Son du jeton"), ("level", "Son des étoiles / records")):
            f.addRow(lbl, self._sound_row(key))
        lay.addWidget(g)

        # --- Données
        g = QGroupBox("Données et sauvegarde")
        v = QVBoxLayout(g)
        v.addWidget(muted(f"Vos statistiques sont enregistrées automatiquement dans : {data_dir()}"))
        row = QHBoxLayout()
        for text, fn in (("Sauvegarder…", ctx.backup), ("Restaurer une sauvegarde…", ctx.restore),
                         ("Exporter CSV", ctx.export_csv), ("Exporter JSON", ctx.export_json),
                         ("Ouvrir le dossier", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        if sys.platform == "win32":
            v.addWidget(self._check(ctx.autostart_enabled(), ctx.set_autostart, "Lancer au démarrage de Windows"))
        reset = QPushButton("Réinitialiser toutes les statistiques…")
        reset.setObjectName("danger")
        reset.clicked.connect(self._reset)
        v.addWidget(reset, 0, Qt.AlignLeft)
        lay.addWidget(g)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(inner))

    # ------------------------------------------------------------------ helpers
    def _check(self, value, fn, text=""):
        cb = QCheckBox(text)
        cb.setChecked(bool(value))
        cb.toggled.connect(fn)
        return cb

    def _set_replays(self, key, value):
        self.ctx.config.set("replays", key, value)
        self.ctx.watcher.enabled = bool(self.ctx.config.get("replays", "enabled", True))
        self.ctx.watcher.poke()

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des replays Fortnite", str(self.ctx.demos_dir()))
        if d:
            self._set_replays("demos_dir", d)
            self.dir_lbl.setText(d)

    def _set_ov(self, key, value):
        self.ctx.config.set("overlay", key, value)
        self.ctx.apply_overlay()

    def _sound_row(self, key):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        cur = self.ctx.config.get("sound", f"{key}_sound", "")
        lbl = muted(cur.split("/")[-1].split("\\")[-1] if cur else "Son intégré", wrap=False)
        choose = QPushButton("Choisir…")
        default = QPushButton("Par défaut")
        test = QPushButton("▶ Tester")

        def pick():
            path, _ = QFileDialog.getOpenFileName(self, "Choisir un son (.wav)", "", "Sons WAV (*.wav)")
            if path:
                self.ctx.config.set("sound", f"{key}_sound", path)
                lbl.setText(path.split("/")[-1])

        def reset():
            self.ctx.config.set("sound", f"{key}_sound", "")
            lbl.setText("Son intégré")

        choose.clicked.connect(pick)
        default.clicked.connect(reset)
        test.clicked.connect(lambda: self.ctx.sound.play(key))
        h.addWidget(lbl, 1)
        for b in (choose, default, test):
            h.addWidget(b)
        return w

    def _reset(self):
        r = QMessageBox.question(self, "Réinitialiser",
                                 "Supprimer DÉFINITIVEMENT toutes les statistiques (coffres, jetons, sessions, niveaux) ?\n"
                                 "Une sauvegarde automatique sera faite avant.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.ctx.reset_stats()
