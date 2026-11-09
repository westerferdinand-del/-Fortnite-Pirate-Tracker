"""Stockage local SQLite des sessions, coffres, jetons et niveaux."""
from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chest_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    ts REAL NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    method TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS token_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    ts REAL NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    total_chests_at INTEGER NOT NULL,
    chests_since_previous INTEGER NOT NULL,
    screenshot TEXT
);
CREATE TABLE IF NOT EXISTS level_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    level INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    total_chests INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_chest_ts ON chest_events(ts);
CREATE INDEX IF NOT EXISTS idx_chest_session ON chest_events(session_id);
"""


@dataclass
class Stats:
    total_chests: int = 0
    total_tokens: int = 0
    since_last_token: int = 0
    today_chests: int = 0
    session_chests: int = 0
    session_tokens: int = 0
    best_session: int = 0
    best_day: int = 0
    fewest_chests_for_token: int | None = None
    tracked_seconds: float = 0.0
    session_seconds: float = 0.0
    sessions_count: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class SessionRow:
    id: int
    started_at: float
    ended_at: float | None
    duration: float
    chests: int
    tokens: int
    since_token_at_end: int


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / "pirate_tracker.db"
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._close_dangling_sessions()

    # ------------------------------------------------------------------ sessions
    def _close_dangling_sessions(self) -> None:
        """Sessions non terminées (crash, extinction du PC) : clôturées à leur dernière activité."""
        with self._lock:
            self.conn.execute("UPDATE sessions SET ended_at = last_seen WHERE ended_at IS NULL")
            self.conn.commit()

    def start_session(self, ts: float | None = None) -> int:
        ts = ts or time.time()
        with self._lock:
            cur = self.conn.execute("INSERT INTO sessions(started_at, last_seen) VALUES (?, ?)", (ts, ts))
            self.conn.commit()
            return int(cur.lastrowid)

    def heartbeat(self, session_id: int, ts: float | None = None) -> None:
        with self._lock:
            self.conn.execute("UPDATE sessions SET last_seen=? WHERE id=?", (ts or time.time(), session_id))
            self.conn.commit()

    def end_session(self, session_id: int, ts: float | None = None) -> None:
        ts = ts or time.time()
        with self._lock:
            self.conn.execute(
                "UPDATE sessions SET ended_at=?, last_seen=? WHERE id=? AND ended_at IS NULL", (ts, ts, session_id)
            )
            # Une session vide de moins de 60 s n'a pas d'intérêt dans l'historique
            self.conn.execute(
                """DELETE FROM sessions WHERE id=? AND (ended_at - started_at) < 60
                   AND NOT EXISTS (SELECT 1 FROM chest_events WHERE session_id=sessions.id)
                   AND NOT EXISTS (SELECT 1 FROM token_events WHERE session_id=sessions.id)""",
                (session_id,),
            )
            self.conn.commit()

    # ------------------------------------------------------------------ events
    def add_chest(self, session_id: int | None, confidence: float = 1.0, method: str = "", ts: float | None = None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO chest_events(session_id, ts, confidence, method) VALUES (?,?,?,?)",
                (session_id, ts or time.time(), float(confidence), method),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def remove_last_chest(self) -> bool:
        """Correction d'un faux positif : supprime le dernier coffre enregistré."""
        with self._lock:
            row = self.conn.execute("SELECT id FROM chest_events ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return False
            self.conn.execute("DELETE FROM chest_events WHERE id=?", (row["id"],))
            self.conn.commit()
            return True

    def add_token(self, session_id: int | None, confidence: float, screenshot: str | None = None, ts: float | None = None) -> dict:
        with self._lock:
            total = self.total_chests()
            last = self.conn.execute("SELECT total_chests_at FROM token_events ORDER BY id DESC LIMIT 1").fetchone()
            since = total - (last["total_chests_at"] if last else 0)
            cur = self.conn.execute(
                """INSERT INTO token_events(session_id, ts, confidence, total_chests_at, chests_since_previous, screenshot)
                   VALUES (?,?,?,?,?,?)""",
                (session_id, ts or time.time(), float(confidence), total, since, screenshot),
            )
            self.conn.commit()
            return {"id": int(cur.lastrowid), "total_chests_at": total, "chests_since_previous": since}

    def add_level_event(self, kind: str, level: int, stars: int, total: int) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO level_events(ts, kind, level, stars, total_chests) VALUES (?,?,?,?,?)",
                (time.time(), kind, level, stars, total),
            )
            self.conn.commit()

    # ------------------------------------------------------------------ queries
    def _scalar(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            row = self.conn.execute(sql, args).fetchone()
        return int(row[0] or 0) if row else 0

    def total_chests(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM chest_events")

    def stats(self, session_id: int | None = None, now: float | None = None) -> Stats:
        now = now or time.time()
        s = Stats()
        with self._lock:
            s.total_chests = self.total_chests()
            s.total_tokens = self._scalar("SELECT COUNT(*) FROM token_events")
            last = self.conn.execute("SELECT total_chests_at FROM token_events ORDER BY id DESC LIMIT 1").fetchone()
            s.since_last_token = s.total_chests - (last["total_chests_at"] if last else 0)
            s.today_chests = self._scalar(
                "SELECT COUNT(*) FROM chest_events WHERE date(ts,'unixepoch','localtime') = date(?,'unixepoch','localtime')",
                (now,),
            )
            s.best_session = self._scalar(
                "SELECT MAX(c) FROM (SELECT COUNT(*) c FROM chest_events WHERE session_id IS NOT NULL GROUP BY session_id)"
            )
            s.best_day = self._scalar(
                "SELECT MAX(c) FROM (SELECT COUNT(*) c FROM chest_events GROUP BY date(ts,'unixepoch','localtime'))"
            )
            row = self.conn.execute(
                "SELECT MIN(chests_since_previous) FROM token_events WHERE chests_since_previous > 0"
            ).fetchone()
            s.fewest_chests_for_token = row[0] if row and row[0] is not None else None
            row = self.conn.execute(
                "SELECT SUM(COALESCE(ended_at, ?) - started_at), COUNT(*) FROM sessions", (now,)
            ).fetchone()
            s.tracked_seconds = float(row[0] or 0.0)
            s.sessions_count = int(row[1] or 0)
            if session_id is not None:
                s.session_chests = self._scalar("SELECT COUNT(*) FROM chest_events WHERE session_id=?", (session_id,))
                s.session_tokens = self._scalar("SELECT COUNT(*) FROM token_events WHERE session_id=?", (session_id,))
                row = self.conn.execute("SELECT started_at, ended_at FROM sessions WHERE id=?", (session_id,)).fetchone()
                if row:
                    s.session_seconds = (row["ended_at"] or now) - row["started_at"]
        return s

    def sessions(self, limit: int = 500) -> list[SessionRow]:
        now = time.time()
        with self._lock:
            rows = self.conn.execute(
                """SELECT s.id, s.started_at, s.ended_at,
                          (SELECT COUNT(*) FROM chest_events c WHERE c.session_id=s.id) AS chests,
                          (SELECT COUNT(*) FROM token_events t WHERE t.session_id=s.id) AS tokens,
                          (SELECT MAX(c.id) FROM chest_events c WHERE c.session_id=s.id) AS last_chest
                   FROM sessions s ORDER BY s.started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            out = []
            for r in rows:
                end_ts = r["ended_at"] or now
                total_at_end = self._scalar("SELECT COUNT(*) FROM chest_events WHERE ts <= ?", (end_ts,))
                tok = self.conn.execute(
                    "SELECT total_chests_at FROM token_events WHERE ts <= ? ORDER BY ts DESC LIMIT 1", (end_ts,)
                ).fetchone()
                since = total_at_end - (tok["total_chests_at"] if tok else 0)
                out.append(SessionRow(r["id"], r["started_at"], r["ended_at"], end_ts - r["started_at"],
                                      r["chests"], r["tokens"], since))
        return out

    def daily_counts(self, days: int = 30) -> list[tuple[str, int]]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT date(ts,'unixepoch','localtime') d, COUNT(*) c FROM chest_events
                   WHERE ts >= ? GROUP BY d ORDER BY d""",
                (time.time() - days * 86400,),
            ).fetchall()
        return [(r["d"], r["c"]) for r in rows]

    def cumulative_series(self, max_points: int = 400) -> list[tuple[float, int]]:
        with self._lock:
            rows = self.conn.execute("SELECT ts FROM chest_events ORDER BY ts").fetchall()
        n = len(rows)
        if n == 0:
            return []
        step = max(1, n // max_points)
        pts = [(rows[i]["ts"], i + 1) for i in range(0, n, step)]
        if pts[-1][1] != n:
            pts.append((rows[-1]["ts"], n))
        return pts

    def tokens(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM token_events ORDER BY ts DESC").fetchall()

    def level_history(self, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM level_events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()

    # ------------------------------------------------------------------ maintenance
    def reset(self) -> None:
        with self._lock:
            self.conn.executescript(
                "DELETE FROM chest_events; DELETE FROM token_events; DELETE FROM level_events; DELETE FROM sessions;"
            )
            self.conn.commit()

    def backup(self, dest: Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(dest))
            self.conn.backup(target)
            target.close()
        return dest

    def restore(self, src: Path) -> None:
        """Remplace toutes les données par celles d'une sauvegarde .db."""
        src_conn = sqlite3.connect(str(src))
        try:
            src_conn.execute("SELECT COUNT(*) FROM chest_events").fetchone()
        finally:
            src_conn.close()
        with self._lock:
            src_conn = sqlite3.connect(str(src))
            src_conn.backup(self.conn)
            src_conn.close()
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def export_json(self, dest: Path) -> Path:
        with self._lock:
            payload = {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "sessions": [dict(r) for r in self.conn.execute("SELECT * FROM sessions")],
                "chest_events": [dict(r) for r in self.conn.execute("SELECT * FROM chest_events")],
                "token_events": [dict(r) for r in self.conn.execute("SELECT * FROM token_events")],
                "level_events": [dict(r) for r in self.conn.execute("SELECT * FROM level_events")],
            }
        Path(dest).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return Path(dest)

    def export_csv(self, dest: Path) -> Path:
        rows = self.sessions(limit=100000)
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["session", "debut", "fin", "duree_min", "coffres", "jetons", "coffres_depuis_dernier_jeton"])
            for r in rows:
                w.writerow([
                    r.id,
                    datetime.fromtimestamp(r.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.fromtimestamp(r.ended_at).strftime("%Y-%m-%d %H:%M:%S") if r.ended_at else "en cours",
                    round(r.duration / 60, 1), r.chests, r.tokens, r.since_token_at_end,
                ])
        return Path(dest)

    def close(self) -> None:
        with self._lock:
            self.conn.close()


def auto_backup(db: Database, keep: int = 10) -> Path:
    from .paths import backups_dir

    dest = backups_dir() / f"auto_{datetime.now():%Y%m%d_%H%M%S}.db"
    db.backup(dest)
    olds = sorted(backups_dir().glob("auto_*.db"))
    for old in olds[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest

