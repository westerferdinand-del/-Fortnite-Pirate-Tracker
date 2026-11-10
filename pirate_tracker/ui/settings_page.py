"""Réglages v2 : compteur, paliers, replays (état, dossier, import), widget, notifications, données."""
from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QProgressBar, QPushButton, QSlider,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import levels, replays
from ..paths import data_dir
from . import theme as T
from .pages import header, page_shell
from .widgets import Card, SettingRow, StatusDot, Toggle, caps, faint, fmt_int, hline


class _ImportWorker(QObject):
    progress = Signal(int, int)
    result = Signal(object)
    done = Signal(str)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths
        self.stop = threading.Event()

    def run(self):
        err = ""
        for i, p in enumerate(self.paths):
            if self.stop.is_set():
                break
            try:
                res = replays.read_replay(p)
                st = Path(p).stat()
                res["_size"], res["_mtime"] = st.st_size, st.st_mtime
                self.result.emit(res)
            except Exception as e:  # noqa: BLE001
                err = str(e)
            self.progress.emit(i + 1, len(self.paths))
        self.done.emit(err)


def _row(*widgets) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    for x in widgets:
        lay.addWidget(x)
    return w


class SettingsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        cfg = ctx.config
        body = QWidget()
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(16)

        # ---------------------------------------------------- compteur
        card = self._card("Compteur")
        self.initial = QSpinBox()
        self.initial.setRange(0, 1_000_000)
        self.initial.setSingleStep(100)
        self.initial.setGroupSeparatorShown(True)
        self.initial.setFixedWidth(130)
        self.initial.setAlignment(Qt.AlignRight)
        self.initial.setValue(ctx.tracker.db.initial_chests)
        apply_btn = QPushButton("Appliquer")
        apply_btn.clicked.connect(self._apply_initial)
        self._add(card, SettingRow("Coffres ouverts avant Pirate Tracker",
                                   "Ajoutés au total affiché partout (widget, vue d'ensemble, niveaux).",
                                   _row(self.initial, apply_btn)))
        self.spins = []
        th = QWidget()
        tl = QHBoxLayout(th)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        for v in ctx.tracker.thresholds:
            sp = QSpinBox()
            sp.setRange(1, 100000)
            sp.setValue(int(v))
            sp.setFixedWidth(64)
            sp.setAlignment(Qt.AlignRight)
            tl.addWidget(sp)
            self.spins.append(sp)
        save = QPushButton("Enregistrer")
        save.clicked.connect(self._save_thresholds)
        tl.addWidget(save)
        self._add(card, SettingRow("Paliers d'un niveau",
                                   "Coffres nécessaires (depuis le début du niveau) pour chacun des 5 paliers.", th),
                  last=True)

        # ---------------------------------------------------- replays
        card = self._card("Replays")
        self.status = StatusDot()
        self.status_msg = faint("")
        st = QWidget()
        sl = QVBoxLayout(st)
        sl.setContentsMargins(0, 12, 0, 12)
        sl.setSpacing(4)
        sl.addWidget(self.status)
        sl.addWidget(self.status_msg)
        card.lay.addWidget(st)
        card.lay.addWidget(hline())
        self.dir_lbl = faint("", wrap=False)
        change = QPushButton("Changer")
        change.setObjectName("ghost")
        change.clicked.connect(self._choose_dir)
        opendir = QPushButton("Ouvrir")
        opendir.setObjectName("ghost")
        opendir.clicked.connect(self._open_dir)
        default = QPushButton("Par défaut")
        default.setObjectName("ghost")
        default.clicked.connect(lambda: self._set_replays("demos_dir", ""))
        dir_row = SettingRow("Dossier des replays", "", _row(opendir, change, default))
        dir_row.layout().itemAt(0).layout().addWidget(self.dir_lbl)
        self._add(card, dir_row)
        self.auto = Toggle(cfg.get("replays", "enabled", True))
        self.auto.toggled.connect(lambda v: self._set_replays("enabled", v))
        self._add(card, SettingRow("Analyse automatique", "Chaque partie est analysée dès que Fortnite a fini "
                                                         "d'écrire son replay.", self.auto))
        self.import_btn = QPushButton("Importer")
        self.import_btn.clicked.connect(self._import_old)
        self.file_btn = QPushButton("Choisir un fichier…")
        self.file_btn.setObjectName("ghost")
        self.file_btn.clicked.connect(self._import_file)
        self.import_row = SettingRow("Anciennes parties", "", _row(self.file_btn, self.import_btn))
        self.import_desc = faint("")
        self.import_desc.setFont(T.font(12))
        self.import_row.layout().itemAt(0).layout().addWidget(self.import_desc)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        self.import_row.layout().itemAt(0).layout().addWidget(self.progress)
        self._add(card, self.import_row)
        help_lbl = faint("Indispensable : dans Fortnite, Réglages → Jeu → Replays → activez « Enregistrer les "
                         "replays ». Fortnite efface ses vieux replays ; les parties déjà analysées restent ici.")
        help_lbl.setFont(T.font(12))
        hw = QWidget()
        hwl = QVBoxLayout(hw)
        hwl.setContentsMargins(0, 12, 0, 4)
        hwl.addWidget(help_lbl)
        card.lay.addWidget(hw)

        # ---------------------------------------------------- widget
        card = self._card("Widget en jeu")
        o = cfg.section("overlay")
        vis = Toggle(o.get("visible", True))
        vis.toggled.connect(lambda v: self._set_ov("visible", v))
        self._add(card, SettingRow("Afficher le widget", "Total de coffres, toujours au premier plan. "
                                                        "Glissez-le pour le déplacer.", vis))
        self.size = self._combo([("small", "Petit"), ("medium", "Moyen"), ("large", "Grand")], o.get("size", "medium"),
                                lambda k: self._set_ov("size", k))
        self._add(card, SettingRow("Taille", "", self.size))
        self.pos = self._combo([("top-left", "En haut à gauche"), ("top-center", "En haut au centre"),
                                ("top-right", "En haut à droite"), ("bottom-left", "En bas à gauche"),
                                ("bottom-right", "En bas à droite"), ("custom", "Position libre")],
                               o.get("position", "top-center"), lambda k: self._set_ov("position", k))
        self._add(card, SettingRow("Position", "", self.pos))
        op = QSlider(Qt.Horizontal)
        op.setRange(30, 100)
        op.setValue(int(float(o.get("opacity", 0.9)) * 100))
        op.setFixedWidth(180)
        op_lbl = faint(f"{op.value()} %", wrap=False)
        op_lbl.setFixedWidth(40)
        op.valueChanged.connect(lambda v: (op_lbl.setText(f"{v} %"), self._set_ov("opacity", v / 100)))
        self._add(card, SettingRow("Opacité", "", _row(op, op_lbl)), last=True)

        # ---------------------------------------------------- notifications
        card = self._card("Notifications et sons")
        n = cfg.section("notifications")
        for key, ttl, desc in (("enabled", "Notifications", "Petites notifications discrètes au-dessus du jeu."),
                               ("on_match", "Fin de partie", "« +12 coffres » quand une partie est analysée."),
                               ("on_level", "Paliers et niveaux", ""), ("on_record", "Records", ""),
                               ("on_token", "Jeton pirate", "Notification Windows quand le jeton est trouvé.")):
            t = Toggle(n.get(key, True))
            t.toggled.connect(lambda v, k=key: cfg.set("notifications", k, v))
            self._add(card, SettingRow(ttl, desc, t))
        s = cfg.section("sound")
        snd = Toggle(s.get("enabled", True))
        snd.toggled.connect(lambda v: cfg.set("sound", "enabled", v))
        self._add(card, SettingRow("Sons", "", snd))
        vol = QSlider(Qt.Horizontal)
        vol.setRange(0, 100)
        vol.setValue(int(float(s.get("volume", 0.7)) * 100))
        vol.setFixedWidth(180)
        vol.valueChanged.connect(lambda v: cfg.set("sound", "volume", v / 100))
        test = QPushButton("Tester")
        test.setObjectName("ghost")
        test.clicked.connect(lambda: ctx.sound.play("match"))
        self._add(card, SettingRow("Volume", "", _row(vol, test)), last=True)

        # ---------------------------------------------------- données
        card = self._card("Données")
        btns = []
        for text, fn in (("Sauvegarder", ctx.backup), ("Restaurer", ctx.restore), ("Exporter CSV", ctx.export_csv),
                         ("Ouvrir le dossier", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.clicked.connect(fn)
            btns.append(b)
        self._add(card, SettingRow("Sauvegarde", "Sauvegarde automatique toutes les 30 minutes et à la fermeture.",
                                   _row(*btns)))
        if sys.platform == "win32":
            auto = Toggle(ctx.autostart_enabled())
            auto.toggled.connect(ctx.set_autostart)
            self._add(card, SettingRow("Lancer au démarrage de Windows", "Réduit, prêt à compter.", auto))
        reset = QPushButton("Tout réinitialiser")
        reset.setObjectName("danger")
        reset.clicked.connect(self._reset)
        self._add(card, SettingRow("Réinitialiser", "Efface toutes les statistiques (une sauvegarde est faite avant).",
                                   reset), last=True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_shell(header("Réglages"), body))
        self._thread = None
        self._old: list[str] = []

    # ---------------------------------------------------------------- construction
    def _card(self, name: str) -> Card:
        self.lay.addWidget(caps(name))
        card = Card(padding=20)
        card.lay.setSpacing(0)
        card.layout().setContentsMargins(20, 6, 20, 6)
        self.lay.addWidget(card)
        return card

    def _add(self, card: Card, row: QWidget, last: bool = False) -> None:
        card.lay.addWidget(row)
        if not last:
            card.lay.addWidget(hline())

    def _combo(self, items, current, on_change) -> QComboBox:
        cb = QComboBox()
        cb.setFixedWidth(200)
        for k, lbl in items:
            cb.addItem(lbl, k)
        cb.setCurrentIndex(max(0, cb.findData(current)))
        cb.currentIndexChanged.connect(lambda _: on_change(cb.currentData()))
        return cb

    # ---------------------------------------------------------------- état / rafraîchissement
    def set_status(self, status: replays.WatcherStatus):
        self.status.set_status(status.level, status.message)
        last = (f" · dernière analyse {datetime.fromtimestamp(status.last_analysis):%H:%M}"
                if status.last_analysis else "")
        self.status_msg.setText(status.message + last)

    def refresh(self, *_):
        ws = self.ctx.watcher.status
        if not ws.message:
            try:
                replays.find_reader()
                ws.reader_ok = True
            except replays.ReaderNotFound:
                ws.reader_ok = False
            d = self.ctx.demos_dir()
            ws.message = ("Lecteur de replays introuvable" if not ws.reader_ok else
                          "Prêt : chaque partie sera analysée à sa fin" if d.is_dir() else
                          "Dossier des replays introuvable : activez « Enregistrer les replays » dans Fortnite")
            ws.level = "active" if ws.reader_ok and d.is_dir() else ("configuring" if ws.reader_ok else "inactive")
        self.set_status(ws)
        d = self.ctx.demos_dir()
        self.dir_lbl.setText(str(d))
        since = float(self.ctx.config.get("replays", "count_since", 0))
        db = self.ctx.tracker.db
        self._old = []
        if d.is_dir():
            for p in d.glob("*.replay"):
                try:
                    stt = p.stat()
                except OSError:
                    continue
                if stt.st_mtime < since and not db.is_processed(str(p), stt.st_size, stt.st_mtime):
                    self._old.append(str(p))
        n = len(self._old)
        self.import_desc.setText(f"{n} replay{'s' if n > 1 else ''} d'avant l'installation, pas encore compté"
                                 f"{'s' if n > 1 else ''}." if n else "Aucun ancien replay à importer.")
        self.import_btn.setEnabled(bool(n) and self._thread is None)
        self.initial.blockSignals(True)
        self.initial.setValue(db.initial_chests)
        self.initial.blockSignals(False)
        for sp, v in zip(self.spins, self.ctx.tracker.thresholds):
            sp.setValue(int(v))

    # ---------------------------------------------------------------- actions
    def _apply_initial(self):
        self.ctx.tracker.set_initial_chests(self.initial.value())
        self.ctx.toast("Total mis à jour", f"{fmt_int(self.ctx.tracker.db.total_chests())} coffres au total")

    def _save_thresholds(self):
        vals = [sp.value() for sp in self.spins]
        try:
            levels.validate_thresholds(vals)
        except ValueError as e:
            QMessageBox.warning(self, "Paliers invalides", str(e))
            return
        self.ctx.config.set("levels", "star_thresholds", vals)
        self.ctx.refresh_all(animate=False)
        self.ctx.toast("Paliers enregistrés", "")

    def _set_replays(self, key, value):
        self.ctx.config.set("replays", key, value)
        self.ctx.watcher.enabled = bool(self.ctx.config.get("replays", "enabled", True))
        self.ctx.watcher.poke()
        self.refresh()

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des replays Fortnite", str(self.ctx.demos_dir()))
        if d:
            self._set_replays("demos_dir", d)

    def _open_dir(self):
        d = self.ctx.demos_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d if d.exists() else d.parent)))

    def _set_ov(self, key, value):
        self.ctx.config.set("overlay", key, value)
        self.ctx.apply_overlay()

    def _import_old(self):
        if self._old:
            self._start_import(list(self._old))

    def _import_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choisir des replays", str(self.ctx.demos_dir()),
                                                "Replays Fortnite (*.replay)")
        if paths:
            self._start_import(paths)

    def _start_import(self, paths: list[str]):
        if self._thread is not None:
            return
        self._results = []
        self._worker = _ImportWorker(paths)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._results.append)
        self._worker.progress.connect(lambda i, n: (self.progress.setRange(0, n), self.progress.setValue(i)))
        self._worker.done.connect(self._on_done)
        self.progress.setVisible(True)
        self.import_btn.setEnabled(False)
        self.file_btn.setEnabled(False)
        self.import_desc.setText(f"Analyse de {len(paths)} replay(s)… environ 2 s chacun.")
        self._thread.start()

    def _on_done(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.progress.setVisible(False)
        self.file_btn.setEnabled(True)
        ok = [r for r in self._results if r.get("ok")]
        gained = self.ctx.tracker.import_results(self._results)
        failed = len(self._results) - len(ok)
        self.refresh()
        msg = f"{len(ok)} partie(s) importée(s), +{fmt_int(gained)} coffres."
        if failed:
            msg += f" {failed} illisible(s)."
        if err:
            msg += f" Erreur : {err}"
        self.import_desc.setText(msg)

    def _reset(self):
        if QMessageBox.question(self, "Tout réinitialiser",
                                "Effacer définitivement toutes les statistiques ?\nUne sauvegarde automatique est "
                                "faite avant.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.ctx.reset_stats()

