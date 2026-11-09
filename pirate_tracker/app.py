"""Point d'entrée de l'application graphique."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME
from .config import Config
from .database import Database, auto_backup
from .detection.templates import TemplateStore
from .engine import DetectionEngine
from .paths import backups_dir, data_dir, templates_dir
from .sound import SoundPlayer
from .tracker import Tracker
from .ui import icons
from .ui import theme as T
from .ui.effects import TokenCelebration, Toast
from .ui.main_window import MainWindow
from .ui.overlay import OverlayWidget


class Bridge(QObject):
    """Transfère les évènements du thread de détection vers le thread de l'interface."""
    chest = Signal(object)
    token = Signal(object, object)
    status = Signal(object)
    metrics = Signal(object)
    fortnite = Signal(bool)
    tracker_event = Signal(str, object)


class AppContext:
    def __init__(self, app: QApplication, video: str | None = None):
        self.app = app
        self.quitting = False
        self.config = Config()
        self.db = Database()
        self.tracker = Tracker(self.db, self.config)
        self.templates = TemplateStore(templates_dir())
        self.sound = SoundPlayer(self.config)
        self.bridge = Bridge()
        self.engine = DetectionEngine(
            self.config.section("detection"), self.templates,
            on_chest=self.bridge.chest.emit, on_token=self.bridge.token.emit,
            on_status=lambda s: self.bridge.status.emit(s), on_metrics=self.bridge.metrics.emit,
            on_fortnite=self.bridge.fortnite.emit, video_source=video,
        )
        self.bridge.chest.connect(lambda ev: self.tracker.record_chest(ev.confidence, ev.method))
        self.bridge.token.connect(lambda ev, frame: self.tracker.record_token(ev.confidence, frame, ev.bbox))
        self.bridge.fortnite.connect(self.tracker.on_fortnite)
        self.bridge.status.connect(self._on_status)
        self.bridge.metrics.connect(self._on_metrics)
        # Les évènements du tracker sont émis dans le thread courant (UI) : on passe par un signal
        # pour rester sûr même si un appel provient d'un autre thread.
        self.tracker.subscribe(lambda k, p: self.bridge.tracker_event.emit(k, p))
        self.bridge.tracker_event.connect(self._on_tracker_event)

        self.toast_w = Toast()
        self.celebration = TokenCelebration()
        self.overlay = OverlayWidget(self.config)
        self.overlay.open_dashboard.connect(self.show_window)
        self.overlay.settings_changed.connect(self._sync_overlay_btn)
        self.window = MainWindow(self)
        self._setup_tray()

        if not self.config.get("detection", "only_when_fortnite_running", True) and not video:
            self.tracker.start_session()

        self._timer = QTimer(interval=1000, timeout=self._tick)
        self._timer.start()
        self._backup_timer = QTimer(interval=30 * 60 * 1000, timeout=lambda: auto_backup(self.db))
        self._backup_timer.start()
        self.refresh_all(animate=False)
        self.apply_overlay()
        self.engine.start()

    # ------------------------------------------------------------------ tray
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(icons.app_icon())
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction("Ouvrir le tableau de bord", self.show_window)
        self.act_overlay = QAction("Afficher le widget", m, checkable=True)
        self.act_overlay.setChecked(self.config.get("overlay", "visible", True))
        self.act_overlay.toggled.connect(lambda v: (self.config.set("overlay", "visible", v), self.apply_overlay()))
        m.addAction(self.act_overlay)
        self.act_det = QAction("Détection active", m, checkable=True)
        self.act_det.setChecked(self.config.get("detection", "enabled", True))
        self.act_det.toggled.connect(lambda v: self.config.set("detection", "enabled", v))
        m.addAction(self.act_det)
        m.addSeparator()
        m.addAction("Quitter", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def tray_message(self, title: str, body: str):
        if self.tray.isVisible() and self.config.get("notifications", "enabled", True):
            self.tray.showMessage(title, body, icons.app_icon(), 3000)

    # ------------------------------------------------------------------ ui helpers
    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def apply_overlay(self):
        self.overlay.apply_settings()
        self.overlay.setVisible(bool(self.config.get("overlay", "visible", True)))
        self._sync_overlay_btn()

    def _sync_overlay_btn(self):
        vis = bool(self.config.get("overlay", "visible", True))
        self.window.widget_btn.setText("Masquer le widget" if vis else "Afficher le widget")
        if hasattr(self, "act_overlay"):
            self.act_overlay.blockSignals(True)
            self.act_overlay.setChecked(vis)
            self.act_overlay.blockSignals(False)

    def toggle_overlay(self):
        self.config.set("overlay", "visible", not self.config.get("overlay", "visible", True))
        self.apply_overlay()

    def toast(self, icon: str, title: str, body: str, duration: float = 2.6):
        if self.config.get("notifications", "enabled", True):
            self.toast_w.notify(icon, title, body, duration)

    def refresh_all(self, animate: bool = True):
        s = self.tracker.stats()
        st = self.tracker.level()
        self.overlay.set_values(s.total_chests, s.total_tokens, st.level, st.stars, s.since_last_token, st.star_progress)
        page = self.window.stack.currentWidget()
        for key, pg in self.window.pages.items():
            if pg is page and hasattr(pg, "refresh"):
                pg.refresh(animate) if key in ("dashboard", "progress") else pg.refresh()

    # ------------------------------------------------------------------ events
    def _on_status(self, status):
        self.overlay.set_status(status.level)
        self.window.pages["dashboard"].set_status(status.level, status.message)
        self.window.pages["detection"].set_status(status)
        self.tray.setToolTip(f"{APP_NAME} — {status.message}")

    def _on_metrics(self, m):
        self.window.pages["detection"].on_metrics(m)

    def _on_tracker_event(self, kind: str, p: dict):
        n = self.config.section("notifications")
        if kind == "chest":
            self.window.pages["detection"].on_chest()
            self.sound.play("chest")
            if n.get("on_chest", True):
                self.toast("chest", f"Coffre n°{p['total']} !", "Compté automatiquement", 1.8)
        elif kind in ("star", "level"):
            self.sound.play("level")
            if n.get("on_level", True):
                if kind == "level":
                    self.toast("trophy", f"NIVEAU {p['level']} !", f"{p['total']} coffres ouverts au total", 3.5)
                else:
                    self.toast("star", f"Étoile {p['stars']} obtenue !", f"Niveau {p['level']} · {p['total']} coffres", 3.0)
        elif kind == "record":
            self.sound.play("record")
            if n.get("on_record", True):
                self.toast("trophy", "Nouveau record !", f"{p['session_chests']} coffres dans cette session", 3.5)
        elif kind == "token":
            self.sound.play("token")
            if n.get("on_token", True):
                self.celebration.play(p["chests_since_previous"], p["stats"].total_tokens)
                self.tray_message("JETON PIRATE TROUVÉ !",
                                  f"Après {p['chests_since_previous']} coffres. Capture enregistrée.")
        if kind in ("chest", "token", "star", "level", "record", "reset", "chest_removed", "session_started",
                    "session_ended"):
            self.refresh_all(animate=kind != "reset")

    def _tick(self):
        self.tracker.heartbeat()
        page = self.window.stack.currentWidget()
        if self.window.isVisible() and page is self.window.pages["dashboard"] and self.tracker.session_id:
            s = self.tracker.stats()
            from .ui.widgets import fmt_duration

            page.cards["session"].set(str(s.session_chests), fmt_duration(s.session_seconds))
            page.cards["time"].set(fmt_duration(s.tracked_seconds))

    # ------------------------------------------------------------------ data actions
    def _ask_save(self, title, default_name, flt):
        path, _ = QFileDialog.getSaveFileName(self.window, title, str(Path.home() / default_name), flt)
        return path

    def export_csv(self):
        p = self._ask_save("Exporter l'historique (CSV)", f"pirate_tracker_{datetime.now():%Y%m%d}.csv", "CSV (*.csv)")
        if p:
            self.db.export_csv(Path(p))
            self.toast("list", "Export terminé", Path(p).name)

    def export_json(self):
        p = self._ask_save("Exporter toutes les données (JSON)", f"pirate_tracker_{datetime.now():%Y%m%d}.json",
                           "JSON (*.json)")
        if p:
            self.db.export_json(Path(p))
            self.toast("list", "Export terminé", Path(p).name)

    def backup(self):
        p = self._ask_save("Sauvegarder la base de données", f"pirate_tracker_sauvegarde_{datetime.now():%Y%m%d}.db",
                           "Base SQLite (*.db)")
        if p:
            self.db.backup(Path(p))
            self.toast("list", "Sauvegarde créée", Path(p).name)

    def restore(self):
        p, _ = QFileDialog.getOpenFileName(self.window, "Restaurer une sauvegarde", str(backups_dir()),
                                           "Base SQLite (*.db)")
        if not p:
            return
        if QMessageBox.question(self.window, "Restaurer",
                                "Remplacer les statistiques actuelles par cette sauvegarde ?") != QMessageBox.Yes:
            return
        auto_backup(self.db)
        sid = self.tracker.session_id
        try:
            self.db.restore(Path(p))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.window, "Restauration impossible", str(e))
            return
        self.tracker.session_id = None
        if sid is not None:
            self.tracker.start_session()
        self.refresh_all(animate=False)

    def reset_stats(self):
        auto_backup(self.db)
        self.tracker.reset_all()

    # ------------------------------------------------------------------ autostart (Windows)
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def autostart_enabled(self) -> bool:
        if sys.platform != "win32":
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, "PirateTracker")
                return True
        except OSError:
            return False

    def set_autostart(self, on: bool):
        if sys.platform != "win32":
            return
        import winreg

        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}" --minimized'
        else:
            cmd = f'"{sys.executable}" -m pirate_tracker --minimized'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "PirateTracker", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, "PirateTracker")
                except OSError:
                    pass

    # ------------------------------------------------------------------ quit
    def quit(self):
        self.quitting = True
        self.engine.stop()
        self.tracker.end_session()
        try:
            auto_backup(self.db)
        except Exception:
            pass
        self.config.save()
        self.db.close()
        self.tray.hide()
        self.app.quit()


def main(argv=None):
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--minimized", action="store_true", help="démarrer réduit (widget seul)")
    parser.add_argument("--video", help="analyser une vidéo à la place de l'écran (démonstration / validation)")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        try:  # icône correcte dans la barre des tâches
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PirateTracker.App")
        except Exception:
            pass

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setFont(T.ui_font(10))
    app.setStyleSheet(T.STYLESHEET)
    app.setWindowIcon(icons.app_icon())

    lock = QLockFile(str(data_dir() / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "Pirate Tracker est déjà lancé (voir l'icône près de l'horloge).")
        return 0

    ctx = AppContext(app, video=args.video)
    if not args.minimized:
        ctx.window.show()
    app.aboutToQuit.connect(lambda: None if ctx.quitting else ctx.quit())
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
