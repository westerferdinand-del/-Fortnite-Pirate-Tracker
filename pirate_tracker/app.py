"""Point d'entrée de l'application graphique."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME
from . import replays
from .config import Config
from .database import Database, auto_backup
from .paths import backups_dir, data_dir
from .sound import SoundPlayer
from .tracker import Tracker
from .ui import icons
from .ui import theme as T
from .ui.effects import Toast
from .ui.main_window import MainWindow
from .ui.overlay import OverlayWidget


class Bridge(QObject):
    """Transfère les évènements du thread de surveillance vers le thread de l'interface."""
    replay_result = Signal(object)
    status = Signal(object)
    tracker_event = Signal(str, object)


class AppContext:
    def __init__(self, app: QApplication, start_watcher: bool = True):
        self.app = app
        self.quitting = False
        self.config = Config()
        self.db = Database()
        self.tracker = Tracker(self.db, self.config)
        self.sound = SoundPlayer(self.config)
        self.bridge = Bridge()

        # Premier lancement : seules les parties jouées à partir de maintenant sont comptées
        # automatiquement (les anciennes peuvent être importées depuis la page Replays).
        if not self.config.get("replays", "count_since", 0):
            self.config.set("replays", "count_since", time.time() - 3600)

        self.watcher = replays.ReplayWatcher(
            demos_dir=self.demos_dir,
            is_processed=self.db.is_processed,
            on_result=self.bridge.replay_result.emit,
            on_status=lambda s: self.bridge.status.emit(s),
            since=lambda: float(self.config.get("replays", "count_since", 0)),
        )
        self.watcher.enabled = bool(self.config.get("replays", "enabled", True))
        self.bridge.replay_result.connect(self._on_replay_result)
        self.bridge.status.connect(self._on_status)
        self.tracker.subscribe(lambda k, p: self.bridge.tracker_event.emit(k, p))
        self.bridge.tracker_event.connect(self._on_tracker_event)

        self.toast_w = Toast()
        self.overlay = OverlayWidget(self.config)
        self.overlay.open_dashboard.connect(self.show_window)
        self.overlay.settings_changed.connect(self._sync_overlay_btn)
        self.window = MainWindow(self)
        self._setup_tray()

        self._backup_timer = QTimer(interval=30 * 60 * 1000, timeout=lambda: auto_backup(self.db))
        self._backup_timer.start()
        self.refresh_all(animate=False)
        self.apply_overlay()
        if start_watcher:
            self.watcher.start()

    # ------------------------------------------------------------------ replays
    @staticmethod
    def default_demos_dir() -> Path:
        return replays.default_demos_dir()

    def demos_dir(self) -> Path:
        custom = self.config.get("replays", "demos_dir", "")
        return Path(custom) if custom else replays.default_demos_dir()

    def _on_replay_result(self, res: dict):
        self.tracker.record_match(res)

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
        m.addAction("Analyser les replays maintenant", self.watcher.poke)
        m.addSeparator()
        m.addAction("Quitter", self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def tray_message(self, title: str, body: str):
        if self.tray.isVisible() and self.config.get("notifications", "enabled", True):
            self.tray.showMessage(title, body, icons.app_icon(), 4000)

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
        self.overlay.set_chests(self.tracker.db.total_chests())
        page = self.window.stack.currentWidget()
        for key, pg in self.window.pages.items():
            if pg is page and hasattr(pg, "refresh"):
                pg.refresh(animate) if key in ("dashboard", "progress") else pg.refresh()

    # ------------------------------------------------------------------ events
    def _on_status(self, status):
        self.overlay.set_status(status.level)
        self.window.pages["dashboard"].set_status(status.level, status.message)
        self.window.pages["replays"].set_status(status)
        self.tray.setToolTip(f"{APP_NAME} — {status.message}")
        if self.window.stack.currentWidget() is self.window.pages["replays"]:
            self.window.pages["replays"].refresh()

    def _on_tracker_event(self, kind: str, p: dict):
        n = self.config.section("notifications")
        if kind == "match" and p.get("notify"):
            if not p.get("ok"):
                self.toast("eye", "Replay illisible", (p.get("error") or "")[:60], 4.0)
            elif n.get("on_match", True):
                c = p["chests"]
                title = f"+{c} coffre{'s' if c > 1 else ''} cette partie" if c else "Aucun coffre cette partie"
                self.sound.play("match")
                self.toast("chest_open", title, f"Total : {p['total']} coffres", 4.0)
                self.tray_message("Partie analysée", f"{title} — total : {p['total']} coffres")
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
                self.toast("trophy", "Nouveau record !", f"{p['match_chests']} coffres en une partie", 3.5)
        elif kind == "token":
            self.sound.play("token")
            if n.get("on_token", True):
                self.tray_message("JETON PIRATE TROUVÉ !", f"Après {p['chests_since_previous']} coffres.")
        elif kind == "imported":
            self.toast("list", "Import terminé", f"{p['count']} partie(s) · +{p['chests']} coffres", 3.5)
        self.refresh_all(animate=kind not in ("reset", "imported", "tokens_rebuilt"))

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
        try:
            self.db.restore(Path(p))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.window, "Restauration impossible", str(e))
            return
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
        self.watcher.stop()
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

    ctx = AppContext(app)
    if not args.minimized:
        ctx.window.show()
    app.aboutToQuit.connect(lambda: None if ctx.quitting else ctx.quit())
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
