"""Page Paramètres."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from ..capture import available_backends
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

        # --- Détection
        g = QGroupBox("Détection")
        f = QFormLayout(g)
        f.setLabelAlignment(Qt.AlignLeft)
        f.setVerticalSpacing(12)
        d = cfg.section("detection")
        self.det_enabled = self._check(d.get("enabled", True), lambda v: self._set_det("enabled", v))
        f.addRow("Détection automatique", self.det_enabled)
        self.only_fn = self._check(d.get("only_when_fortnite_running", True),
                                   lambda v: self._set_det("only_when_fortnite_running", v))
        f.addRow("Uniquement quand Fortnite est lancé", self.only_fn)
        self.backend = QComboBox()
        names = {"auto": "Automatique (recommandé)", "dxcam": "DXGI Desktop Duplication (rapide)",
                 "mss": "GDI (compatible)"}
        for key in ["auto"] + available_backends():
            self.backend.addItem(names.get(key, key), key)
        self.backend.setCurrentIndex(max(0, self.backend.findData(d.get("capture_backend", "auto"))))
        self.backend.currentIndexChanged.connect(lambda _: self._set_det("capture_backend", self.backend.currentData(), True))
        f.addRow("Mode de capture", self.backend)
        self.monitor = QSpinBox()
        self.monitor.setRange(1, 6)
        self.monitor.setValue(int(d.get("monitor", 1)))
        self.monitor.valueChanged.connect(lambda v: self._set_det("monitor", v, True))
        f.addRow("Écran du jeu (n°)", self.monitor)
        self.mode = QComboBox()
        self.mode.addItem("Invite « Fouiller » + éclat (fiable, calibrage requis)", "prompt+burst")
        self.mode.addItem("Éclat seul (sans calibrage, moins fiable)", "burst")
        self.mode.setCurrentIndex(max(0, self.mode.findData(d.get("chest_mode", "prompt+burst"))))
        self.mode.currentIndexChanged.connect(lambda _: self._set_det("chest_mode", self.mode.currentData(), True))
        f.addRow("Méthode de détection des coffres", self.mode)
        self.fps = QSpinBox()
        self.fps.setRange(5, 30)
        self.fps.setValue(int(d.get("fps", 15)))
        self.fps.setSuffix(" images/s")
        self.fps.valueChanged.connect(lambda v: self._set_det("fps", v))
        f.addRow("Fréquence d'analyse", self.fps)
        self.sens = _slider(50, 200, int(float(d.get("burst_sensitivity", 1.0)) * 100))
        self.sens_lbl = QLabel()
        self.sens.valueChanged.connect(self._sens_changed)
        row = QHBoxLayout()
        row.addWidget(self.sens, 1)
        row.addWidget(self.sens_lbl)
        f.addRow("Sensibilité de l'éclat", row)
        self.pthr = _slider(55, 95, int(float(d.get("prompt_threshold", 0.72)) * 100))
        self.pthr_lbl = QLabel()
        self.pthr.valueChanged.connect(self._pthr_changed)
        row = QHBoxLayout()
        row.addWidget(self.pthr, 1)
        row.addWidget(self.pthr_lbl)
        f.addRow("Seuil de reconnaissance de l'invite", row)
        self.cool = QSpinBox()
        self.cool.setRange(1, 10)
        self.cool.setValue(int(round(float(d.get("cooldown_s", 2.5)))))
        self.cool.setSuffix(" s")
        self.cool.valueChanged.connect(lambda v: self._set_det("cooldown_s", float(v), True))
        f.addRow("Délai anti double-comptage", self.cool)
        self.tok = self._check(d.get("token_enabled", True), lambda v: self._set_det("token_enabled", v))
        f.addRow("Détection du jeton pirate", self.tok)
        self._sens_changed(self.sens.value(), save=False)
        self._pthr_changed(self.pthr.value(), save=False)
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
        f.addRow("Afficher le niveau", self._check(o.get("show_level", True), lambda v: self._set_ov("show_level", v)))
        f.addRow("Afficher « depuis le dernier jeton »",
                 self._check(o.get("show_since_token", True), lambda v: self._set_ov("show_since_token", v)))
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
        for key, lbl in (("on_chest", "… à chaque coffre détecté"), ("on_token", "… quand un jeton est détecté"),
                         ("on_level", "… à chaque nouvelle étoile / niveau"), ("on_record", "… quand je bats mon record")):
            f.addRow(lbl, self._check(n.get(key, True), lambda v, k=key: cfg.set("notifications", k, v)))
        s = cfg.section("sound")
        f.addRow("Sons", self._check(s.get("enabled", True), lambda v: cfg.set("sound", "enabled", v)))
        self.vol = _slider(0, 100, int(float(s.get("volume", 0.7)) * 100))
        self.vol.valueChanged.connect(lambda v: cfg.set("sound", "volume", v / 100))
        f.addRow("Volume", self.vol)
        for key, lbl in (("chest", "Son du coffre"), ("token", "Son du jeton"), ("level", "Son des étoiles / records")):
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

    def _set_det(self, key, value, reload=False):
        self.ctx.config.set("detection", key, value)
        if reload:
            self.ctx.engine.reload()

    def _set_ov(self, key, value):
        self.ctx.config.set("overlay", key, value)
        self.ctx.apply_overlay()

    def _sens_changed(self, v, save=True):
        self.sens_lbl.setText(f"×{v / 100:.2f}")
        if save:
            self._set_det("burst_sensitivity", v / 100, True)

    def _pthr_changed(self, v, save=True):
        self.pthr_lbl.setText(f"{v / 100:.2f}")
        if save:
            self._set_det("prompt_threshold", v / 100, True)

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
