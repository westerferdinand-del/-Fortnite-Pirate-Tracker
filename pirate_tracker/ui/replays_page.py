"""Page Replays : état de l'analyse, activation des replays dans Fortnite, import des anciennes parties."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from .. import replays
from . import theme as T
from .pages import cell, make_table, scroll_page
from .widgets import Card, StatusPill, h1, h2, muted


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


class ReplaysPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(h1("ANALYSE DES REPLAYS"), 1)
        self.status = StatusPill()
        top.addWidget(self.status)
        lay.addLayout(top)

        # --- état
        st = Card()
        sl = QGridLayout(st)
        sl.setContentsMargins(20, 16, 20, 16)
        self.lbl_msg = QLabel("—")
        self.lbl_msg.setFont(T.ui_font(10, QFont.Bold))
        self.lbl_msg.setWordWrap(True)
        self.lbl_dir = muted("Dossier : —")
        self.lbl_reader = muted("Lecteur : —")
        self.lbl_last = muted("Dernière analyse : —")
        sl.addWidget(self.lbl_msg, 0, 0, 1, 3)
        sl.addWidget(self.lbl_dir, 1, 0, 1, 3)
        sl.addWidget(self.lbl_reader, 2, 0)
        sl.addWidget(self.lbl_last, 2, 1)
        row = QHBoxLayout()
        for text, fn in (("Analyser maintenant", self._poke), ("Ouvrir le dossier des replays", self._open_dir),
                         ("Changer de dossier…", self._choose_dir)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        sl.addLayout(row, 3, 0, 1, 3)
        lay.addWidget(st)

        # --- activer les replays
        how = Card()
        hl = QVBoxLayout(how)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.addWidget(h2("Étape indispensable : activer les replays dans Fortnite (une seule fois)"))
        steps = QLabel(
            "<ol style='margin-left:-20px; line-height:150%'>"
            "<li>Dans Fortnite, ouvrez le <b>menu</b> (en haut à droite) → <b>Réglages</b> ⚙.</li>"
            "<li>Onglet <b>Jeu</b> → section <b>Replays</b>.</li>"
            "<li>Activez <b>« Enregistrer les replays »</b> (<i>Record Replays</i>) — et sur PC, si l'option existe, "
            "<b>« Enregistrer les replays en Battle Royale »</b>.</li>"
            "<li>Jouez normalement : à la fin de chaque partie, Fortnite écrit le replay et "
            "Pirate Tracker met le compteur à jour tout seul.</li></ol>")
        steps.setTextFormat(Qt.RichText)
        steps.setWordWrap(True)
        hl.addWidget(steps)
        hl.addWidget(muted("Remarque : Fortnite ne garde qu'un nombre limité de replays et supprime les plus anciens. "
                           "Pirate Tracker enregistre les résultats dans sa propre base : rien n'est perdu quand "
                           "Fortnite efface un replay déjà analysé."))
        lay.addWidget(how)

        # --- replays présents
        lst = Card()
        ll = QVBoxLayout(lst)
        ll.setContentsMargins(20, 16, 20, 16)
        ll.addWidget(h2("Replays trouvés"))
        ll.addWidget(muted("Les replays antérieurs à l'installation ne sont pas comptés automatiquement. "
                           "Vous pouvez les importer pour retrouver vos coffres passés."))
        self.table = make_table(["Fichier", "Date", "Taille", "État"], 260, stretch=0)
        ll.addWidget(self.table)
        row = QHBoxLayout()
        self.btn_import = QPushButton("Importer les anciens replays")
        self.btn_import.setObjectName("primary")
        self.btn_import.clicked.connect(self._import_old)
        self.btn_file = QPushButton("Analyser un fichier .replay…")
        self.btn_file.clicked.connect(self._import_file)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        row.addWidget(self.btn_import)
        row.addWidget(self.btn_file)
        row.addWidget(self.progress, 1)
        ll.addLayout(row)
        self.import_msg = muted("")
        ll.addWidget(self.import_msg)
        lay.addWidget(lst)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(inner))
        self._thread = None
        self._worker = None

    # ------------------------------------------------------------------ état
    def set_status(self, status: replays.WatcherStatus):
        self.status.set_status(status.level, status.message)
        self.lbl_msg.setText(status.message)
        self.lbl_dir.setText(f"Dossier : {status.demos_dir or self.ctx.demos_dir()}")
        self.lbl_reader.setText("Lecteur de replays : " + ("OK" if status.reader_ok else "introuvable"))
        if status.last_analysis:
            self.lbl_last.setText(f"Dernière analyse : {datetime.fromtimestamp(status.last_analysis):%d/%m %H:%M:%S}")

    def refresh(self, *_):
        ws = self.ctx.watcher.status
        if not ws.message:  # pas encore de passage du surveillant : état calculé maintenant
            try:
                replays.find_reader()
                ws.reader_ok = True
            except replays.ReaderNotFound:
                ws.reader_ok = False
            ws.demos_dir = str(self.ctx.demos_dir())
            ws.message = ("Lecteur de replays introuvable" if not ws.reader_ok else
                          "Prêt : chaque partie sera analysée automatiquement à sa fin"
                          if self.ctx.demos_dir().is_dir() else
                          "Dossier des replays introuvable : activez « Enregistrer les replays » dans Fortnite")
            ws.level = "active" if ws.reader_ok and self.ctx.demos_dir().is_dir() else (
                "configuring" if ws.reader_ok else "inactive")
        self.set_status(ws)
        d = self.ctx.demos_dir()
        files = sorted(d.glob("*.replay"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
        since = float(self.ctx.config.get("replays", "count_since", 0))
        db = self.ctx.tracker.db
        self.table.setRowCount(len(files))
        self._old = []
        pending = set(self.ctx.watcher.status.pending)
        for i, p in enumerate(files):
            st = p.stat()
            if db.is_processed(str(p), st.st_size, st.st_mtime):
                state, color = "Comptée", T.GREEN
            elif p.name in pending:
                state, color = "En attente (partie en cours ?)", T.ORANGE
            elif st.st_mtime < since:
                state, color = "Ancienne — à importer", T.MUTED
                self._old.append(str(p))
            else:
                state, color = "Analyse prochaine", T.BLUE
            self.table.setItem(i, 0, cell(p.name, Qt.AlignLeft | Qt.AlignVCenter))
            self.table.setItem(i, 1, cell(datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")))
            self.table.setItem(i, 2, cell(f"{st.st_size / 1e6:.1f} Mo"))
            self.table.setItem(i, 3, cell(state, color=color))
        self.btn_import.setEnabled(bool(self._old) and self._thread is None)
        self.btn_import.setText(f"Importer les anciens replays ({len(self._old)})")

    # ------------------------------------------------------------------ actions
    def _poke(self):
        self.ctx.watcher.poke()
        self.ctx.toast("eye", "Analyse", "Recherche de nouveaux replays…")

    def _open_dir(self):
        d = self.ctx.demos_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d if d.exists() else d.parent)))

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des replays Fortnite", str(self.ctx.demos_dir()))
        if d:
            self.ctx.config.set("replays", "demos_dir", d)
            self.ctx.watcher.poke()
            self.refresh()

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
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.btn_import.setEnabled(False)
        self.btn_file.setEnabled(False)
        self.import_msg.setText(f"Analyse de {len(paths)} replay(s)… (environ 2 s chacun)")
        self._t0 = time.time()
        self._thread.start()

    def _on_progress(self, i, n):
        self.progress.setValue(i)

    def _on_done(self, err: str):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.progress.setVisible(False)
        self.btn_file.setEnabled(True)
        ok = [r for r in self._results if r.get("ok")]
        gained = self.ctx.tracker.import_results(self._results)
        failed = len(self._results) - len(ok)
        msg = f"{len(ok)} partie(s) importée(s), {gained} coffre(s) ajouté(s)."
        if failed:
            msg += f" {failed} replay(s) illisible(s)."
        if err:
            msg += f" Erreur : {err}"
        self.import_msg.setText(msg)
        self.refresh()
        if failed and not ok:
            QMessageBox.warning(self, "Import", msg)
