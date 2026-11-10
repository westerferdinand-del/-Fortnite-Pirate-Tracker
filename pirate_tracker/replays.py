"""Lecture des replays Fortnite à la fin de chaque partie.

Fortnite enregistre chaque partie dans ``%LOCALAPPDATA%\\FortniteGame\\Saved\\Demos``
(option « Enregistrer les replays » à activer dans les réglages du jeu). Ce module :

* localise le lecteur de replays (``PirateReplayReader``, programme C# fourni avec
  l'application) et l'exécute sur un fichier ``.replay`` ;
* surveille le dossier des replays et analyse chaque nouvelle partie dès que le
  fichier est terminé (jamais pendant l'enregistrement : un replay incomplet
  donnerait un nombre de coffres partiel).

Aucune interaction avec le jeu : on lit seulement des fichiers que Fortnite écrit
lui-même sur le disque.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import process_watch
from .paths import resource_path

STABLE_SECONDS = 30.0  # le fichier ne doit plus changer pendant ce délai
POLL_SECONDS = 10.0
READER_TIMEOUT = 300


def default_demos_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "FortniteGame" / "Saved" / "Demos"


class ReaderNotFound(RuntimeError):
    pass


def find_reader() -> list[str]:
    """Commande pour lancer le lecteur de replays.

    Ordre : variable PIRATE_REPLAY_READER (exe ou .dll), exe embarqué dans
    l'application, puis version compilée en développement (``dotnet <dll>``).
    """
    candidates: list[Path] = []
    env = os.environ.get("PIRATE_REPLAY_READER")
    if env:
        candidates.append(Path(env))
    exe = "PirateReplayReader.exe" if sys.platform == "win32" else "PirateReplayReader"
    candidates.append(resource_path("bin", exe))
    repo = Path(__file__).resolve().parent.parent / "replay_reader" / "PirateReplayReader" / "bin"
    for cfg in ("Release", "Debug"):
        candidates.append(repo / cfg / "net10.0" / "PirateReplayReader.dll")
    for c in candidates:
        if c.is_file():
            if c.suffix == ".dll":
                dotnet = shutil.which("dotnet")
                if dotnet:
                    return [dotnet, str(c)]
                continue
            return [str(c)]
    raise ReaderNotFound("Lecteur de replays introuvable (PirateReplayReader).")


def read_replays(paths: list[Path | str], timeout: float = READER_TIMEOUT) -> list[dict]:
    """Analyse un ou plusieurs replays ; renvoie un dict par fichier (clé ``ok``)."""
    if not paths:
        return []
    cmd = find_reader() + [str(p) for p in paths]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW : pas de console qui clignote
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, **kwargs)
    out = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not out:
        err = proc.stderr.decode("utf-8", "replace").strip()[-500:]
        out = [{"ok": False, "file": str(p), "error": err or f"code {proc.returncode}"} for p in paths]
    return out


def read_replay(path: Path | str, timeout: float = READER_TIMEOUT) -> dict:
    return read_replays([path], timeout)[0]


@dataclass
class FileState:
    size: int
    mtime: float
    seen_at: float


@dataclass
class WatcherStatus:
    level: str = "inactive"  # active / configuring / inactive
    message: str = ""
    demos_dir: str = ""
    reader_ok: bool = False
    fortnite_running: bool = False
    pending: list[str] = field(default_factory=list)
    last_analysis: float | None = None


class ReplayWatcher:
    """Surveille le dossier des replays et analyse chaque partie terminée.

    ``is_processed(path, size, mtime)`` indique si ce fichier, dans cet état, a déjà
    été compté (fourni par la base de données). ``on_result(dict)`` est appelé pour
    chaque replay analysé, depuis le thread du surveillant.
    """

    def __init__(self, demos_dir: Callable[[], Path], is_processed: Callable[[str, int, float], bool],
                 on_result: Callable[[dict], None], on_status: Callable[[WatcherStatus], None] | None = None,
                 since: Callable[[], float] | None = None, stable_seconds: float = STABLE_SECONDS,
                 poll_seconds: float = POLL_SECONDS, reader: Callable[[list], list[dict]] = read_replays):
        self.demos_dir = demos_dir
        self.is_processed = is_processed
        self.on_result = on_result
        self.on_status = on_status
        self.since = since or (lambda: 0.0)
        self.stable_seconds = stable_seconds
        self.poll_seconds = poll_seconds
        self.reader = reader
        self.status = WatcherStatus()
        self._files: dict[str, FileState] = {}
        self._failures: dict[str, tuple[int, float]] = {}
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.enabled = True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="replay-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def poke(self) -> None:
        """Force une vérification immédiate."""
        self._wake.set()

    def _set_status(self, level: str, message: str) -> None:
        changed = (level, message) != (self.status.level, self.status.message)
        self.status.level, self.status.message = level, message
        if self.on_status and changed:
            self.on_status(self.status)

    def _run(self) -> None:
        last_proc = 0.0
        while not self._stop.is_set():
            try:
                now = time.time()
                if now - last_proc > 5:
                    last_proc = now
                    self.status.fortnite_running = process_watch.fortnite_pid() is not None
                self.scan(now)
            except Exception as e:  # le surveillant ne doit jamais s'arrêter
                self._set_status("configuring", f"Erreur pendant l'analyse : {e}")
            self._wake.wait(self.poll_seconds)
            self._wake.clear()

    def scan(self, now: float | None = None) -> list[dict]:
        """Un passage de surveillance. Renvoie les résultats produits (utile aux tests)."""
        now = time.time() if now is None else now
        if not self.enabled:
            self._set_status("inactive", "Analyse des replays désactivée dans les paramètres")
            return []
        d = self.demos_dir()
        self.status.demos_dir = str(d)
        try:
            find_reader() if self.reader is read_replays else None
            self.status.reader_ok = True
        except ReaderNotFound as e:
            self.status.reader_ok = False
            self._set_status("inactive", str(e))
            return []
        if not d.is_dir():
            self._set_status("configuring", "Dossier des replays introuvable : activez « Enregistrer les replays » "
                                            "dans Fortnite et jouez une partie")
            return []

        since = self.since()
        ready, waiting = [], []
        current = set()
        for p in d.glob("*.replay"):
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            current.add(key)
            if st.st_mtime < since:
                continue  # replay antérieur à l'installation : importable à la main
            if self.is_processed(key, st.st_size, st.st_mtime):
                continue
            fail = self._failures.get(key)
            if fail and fail[0] == st.st_size and now - fail[1] < 600:
                continue  # échec récent sur ce même fichier : on réessaie plus tard
            prev = self._files.get(key)
            if prev is None or prev.size != st.st_size or prev.mtime != st.st_mtime:
                self._files[key] = FileState(st.st_size, st.st_mtime, now)
                waiting.append(p.name)
                continue
            if now - max(prev.seen_at, st.st_mtime) < self.stable_seconds:
                waiting.append(p.name)
                continue
            ready.append(p)
        for k in list(self._files):
            if k not in current:
                del self._files[k]

        self.status.pending = waiting
        results = []
        if ready:
            self._set_status("active", f"Analyse de {len(ready)} replay(s)…")
            for res in self.reader([str(p) for p in ready]):
                path = res.get("file", "")
                if res.get("ok") and res.get("is_live"):
                    # Encore en cours d'enregistrement : on attend la fin de la partie
                    self._files.pop(path, None)
                    continue
                if not res.get("ok"):
                    try:
                        self._failures[path] = (Path(path).stat().st_size, now)
                    except OSError:
                        pass
                try:
                    st = Path(path).stat()
                    res["_size"], res["_mtime"] = st.st_size, st.st_mtime
                except OSError:
                    res["_size"], res["_mtime"] = 0, 0.0
                results.append(res)
                self.on_result(res)
            self.status.last_analysis = now

        if waiting:
            msg = ("Partie en cours d'enregistrement — le compteur sera mis à jour à la fin de la partie"
                   if self.status.fortnite_running else "Replay en attente de finalisation…")
            self._set_status("active", msg)
        else:
            self._set_status("active", "Prêt : chaque partie sera analysée automatiquement à sa fin")
        return results
