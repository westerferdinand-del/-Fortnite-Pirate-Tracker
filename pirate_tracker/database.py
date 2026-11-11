"""Stockage local SQLite : parties (une par replay), coffres, objets obtenus, jetons, niveaux."""
from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .items import chest_category
from .paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    replay_path TEXT NOT NULL UNIQUE,
    replay_size INTEGER NOT NULL DEFAULT 0,
    replay_mtime REAL NOT NULL DEFAULT 0,
    session_id TEXT,
    started_at REAL NOT NULL,
    duration REAL NOT NULL DEFAULT 0,
    chests INTEGER NOT NULL DEFAULT 0,
    placement INTEGER,
    total_players INTEGER,
    eliminations INTEGER,
    playlist TEXT,
    player_name TEXT,
    branch TEXT,
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    warnings TEXT,
    diagnostics TEXT,
    processed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chest_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    t_in_match REAL,
    kind TEXT NOT NULL DEFAULT '',
    how TEXT NOT NULL DEFAULT 'ouvert',
    special INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL DEFAULT 'standard',
    chest_id INTEGER,
    direct INTEGER NOT NULL DEFAULT 1,
    reopen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    item TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS token_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
    ts REAL NOT NULL,
    item TEXT,
    total_chests_at INTEGER NOT NULL,
    chests_since_previous INTEGER NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_chest_match ON chest_events(match_id);
CREATE INDEX IF NOT EXISTS idx_items_match ON items(match_id);
"""


# Informations techniques conservées pour comprendre une analyse surprenante (ex. 0 coffre)
DIAG_KEYS = ("reader_version", "branch", "owner_found", "relevancy_pawns", "pawns_seen", "owner_pawns", "chests_seen",
             "chest_searches_seen", "chests_opened_by_anyone", "aliased_classes", "special_chest_classes",
             "chest_classes_opened", "other_containers_searched", "chests_destroyed_unattributed", "partial",
             "duration_s", "unique_chests", "total_openings", "inferred_openings", "owner_pawn_ids",
             "class_decisions", "decisions")


@dataclass
class Stats:
    total_chests: int = 0
    initial_chests: int = 0  # coffres ouverts avant Pirate Tracker (saisis par l'utilisateur)
    total_broken: int = 0
    total_special: int = 0
    total_reopens: int = 0
    unique_chests: int = 0  # coffres différents (un coffre rouvert ne compte qu'une fois ici)
    total_tokens: int = 0
    since_last_token: int = 0
    today_chests: int = 0
    last_match_chests: int | None = None
    last_match_at: float | None = None
    last_match_placement: int | None = None
    best_match: int = 0
    best_day: int = 0
    fewest_chests_for_token: int | None = None
    tracked_seconds: float = 0.0
    matches_count: int = 0
    distinct_items: int = 0


@dataclass
class MatchRow:
    id: int
    started_at: float
    duration: float
    chests: int
    broken: int
    special: int
    reopens: int
    unique_chests: int
    tokens: int
    placement: int | None
    total_players: int | None
    eliminations: int | None
    playlist: str | None
    ok: bool
    error: str | None
    warnings: list
    replay_path: str
    diagnostics: dict


def _ts(iso: str | None, fallback: float) -> float:
    if not iso:
        return fallback
    try:
        s = iso.replace("Z", "")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        t = dt.timestamp()
        return t if t > 946684800 else fallback  # date invalide (avant 2000)
    except ValueError:
        return fallback


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / "pirate_tracker.db"
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate_v1()
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(chest_events)")}
        for col, ddl in (("how", "TEXT NOT NULL DEFAULT 'ouvert'"), ("special", "INTEGER NOT NULL DEFAULT 0"),
                         ("category", "TEXT NOT NULL DEFAULT 'standard'"), ("chest_id", "INTEGER"),
                         ("direct", "INTEGER NOT NULL DEFAULT 1"), ("reopen", "INTEGER NOT NULL DEFAULT 0")):
            if col not in cols:  # bases créées avant l'ajout de « cassé / spécial / catégorie »
                self.conn.execute(f"ALTER TABLE chest_events ADD COLUMN {col} {ddl}")
        self._recategorize_chests()
        if "diagnostics" not in {r[1] for r in self.conn.execute("PRAGMA table_info(matches)")}:
            self.conn.execute("ALTER TABLE matches ADD COLUMN diagnostics TEXT")
        self.conn.commit()

    def _recategorize_chests(self) -> None:
        """Corrige les coffres enregistrés par d'anciennes versions.

        Avant la 2.1, tout coffre d'une classe autre que l'ancien coffre standard était marqué
        « spécial », y compris les coffres normaux d'une nouvelle saison. On recalcule à partir
        du nom de classe enregistré.
        """
        from .items import chest_category

        if self.get_meta("chest_categories_v") == "2":
            return
        rows = self.conn.execute("SELECT id, kind FROM chest_events").fetchall()
        updates = [(cat, 1 if special else 0, r["id"]) for r in rows for cat, special in [chest_category(r["kind"])]]
        self.conn.executemany("UPDATE chest_events SET category=?, special=? WHERE id=?", updates)
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('chest_categories_v', '2')")

    def _migrate_v1(self) -> None:
        """La version 1 (reconnaissance d'écran) utilisait d'autres tables : on les met de côté."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(chest_events)")}
        if cols and "match_id" not in cols:
            for t in ("chest_events", "token_events", "sessions"):
                try:
                    self.conn.execute(f"ALTER TABLE {t} RENAME TO v1_{t}")
                except sqlite3.OperationalError:
                    pass
            self.conn.commit()

    # ------------------------------------------------------------------ replays
    def is_processed(self, path: str, size: int, mtime: float) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT replay_size, replay_mtime FROM matches WHERE replay_path=?", (path,)
            ).fetchone()
        return bool(row) and row["replay_size"] == size and abs(row["replay_mtime"] - mtime) < 1e-3

    def upsert_match(self, res: dict, size: int = 0, mtime: float = 0.0) -> dict:
        """Enregistre (ou remplace) le résultat d'analyse d'un replay.

        Retourne ``{match_id, chests, delta, items, replaced}`` où ``delta`` est la
        variation du nombre total de coffres (0 si le replay avait déjà été compté).
        """
        path = res.get("file") or ""
        now = time.time()
        fallback = (mtime - float(res.get("duration_s") or 0)) if mtime else now
        started = _ts(res.get("started_utc"), fallback)
        chests = (res.get("chests") or []) if res.get("ok") else []
        items = (res.get("items") or []) if res.get("ok") else []
        with self._lock:
            old = self.conn.execute("SELECT id, chests FROM matches WHERE replay_path=?", (path,)).fetchone()
            old_chests = old["chests"] if old else 0
            if old:
                self.conn.execute("DELETE FROM matches WHERE id=?", (old["id"],))  # cascade : coffres, objets, jetons
            cur = self.conn.execute(
                """INSERT INTO matches(replay_path, replay_size, replay_mtime, session_id, started_at, duration, chests,
                       placement, total_players, eliminations, playlist, player_name, branch, ok, error, warnings,
                       diagnostics, processed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (path, int(size), float(mtime), res.get("session_id"), started, float(res.get("duration_s") or 0),
                 len(chests), res.get("placement"), res.get("total_players"), res.get("eliminations"),
                 res.get("playlist"), res.get("player_name"), res.get("branch"), 1 if res.get("ok") else 0,
                 res.get("error"), json.dumps(res.get("warnings") or [], ensure_ascii=False),
                 json.dumps({k: res.get(k) for k in DIAG_KEYS if k in res}, ensure_ascii=False), now),
            )
            mid = int(cur.lastrowid)
            self.conn.executemany(
                "INSERT INTO chest_events(match_id, ts, t_in_match, kind, how, special, category, chest_id, direct, reopen)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(mid, started + float(c.get("t", 0)), float(c.get("t", 0)), c.get("kind", ""),
                  "cassé" if c.get("how") == "cassé" else "ouvert", 1 if chest_category(c.get("kind", ""))[1] else 0,
                  chest_category(c.get("kind", ""))[0], c.get("id"), 0 if c.get("direct") is False else 1,
                  1 if c.get("reopen") else 0) for c in chests],
            )
            self.conn.executemany(
                "INSERT INTO items(match_id, ts, item, count) VALUES (?,?,?,?)",
                [(mid, started + float(i.get("t", 0)), i.get("item", ""), int(i.get("count") or 0)) for i in items],
            )
            self.conn.commit()
        return {"match_id": mid, "chests": len(chests), "delta": len(chests) - old_chests,
                "items": items, "replaced": bool(old), "started_at": started}

    def match_chest_events(self, match_id: int) -> list[dict]:
        """Coffres d'une partie, dans l'ordre : moment, ouvert / cassé, réouverture, type."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT t_in_match, how, reopen, category, kind FROM chest_events WHERE match_id=? ORDER BY t_in_match",
                (match_id,)).fetchall()
        return [{"t": r["t_in_match"] or 0.0, "how": r["how"], "reopen": bool(r["reopen"]), "category": r["category"],
                 "kind": r["kind"]} for r in rows]

    def match_chest_types(self, match_id: int) -> list[tuple[str, int]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT category, COUNT(*) c FROM chest_events WHERE match_id=? GROUP BY category ORDER BY c DESC",
                (match_id,)).fetchall()
        return [(r["category"], r["c"]) for r in rows]

    def delete_match(self, match_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM matches WHERE id=?", (match_id,))
            self.conn.commit()

    # ------------------------------------------------------------------ jetons / niveaux
    def add_token(self, match_id: int | None, item: str, ts: float | None = None) -> dict:
        with self._lock:
            ts = ts or time.time()
            total = self._scalar("SELECT COUNT(*) FROM chest_events WHERE ts <= ?", (ts,)) + self.initial_chests
            last = self.conn.execute("SELECT total_chests_at FROM token_events ORDER BY ts DESC LIMIT 1").fetchone()
            since = total - (last["total_chests_at"] if last else 0)
            cur = self.conn.execute(
                """INSERT INTO token_events(match_id, ts, item, total_chests_at, chests_since_previous)
                   VALUES (?,?,?,?,?)""",
                (match_id, ts, item, total, since),
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

    # ------------------------------------------------------------------ requêtes
    def _scalar(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            row = self.conn.execute(sql, args).fetchone()
        return int(row[0] or 0) if row else 0

    @property
    def initial_chests(self) -> int:
        """Coffres ouverts avant l'installation, ajoutés au total (réglage utilisateur)."""
        try:
            return max(0, int(self.get_meta("initial_chests", "0") or 0))
        except ValueError:
            return 0

    def set_initial_chests(self, n: int) -> None:
        self.set_meta("initial_chests", str(max(0, int(n))))

    def counted_chests(self) -> int:
        """Coffres réellement comptés par Pirate Tracker (sans les coffres d'avant)."""
        return self._scalar("SELECT COUNT(*) FROM chest_events")

    def total_chests(self) -> int:
        return self.counted_chests() + self.initial_chests

    def stats(self, now: float | None = None) -> Stats:
        now = now or time.time()
        s = Stats()
        with self._lock:
            s.total_chests = self.total_chests()
            s.initial_chests = self.initial_chests
            s.total_broken = self._scalar("SELECT COUNT(*) FROM chest_events WHERE how='cassé'")
            s.total_special = self._scalar("SELECT COUNT(*) FROM chest_events WHERE special=1")
            s.total_reopens = self._scalar("SELECT COUNT(*) FROM chest_events WHERE reopen=1")
            # Coffres uniques : par partie, identifiant de coffre (les anciennes lignes sans identifiant comptent 1)
            s.unique_chests = self._scalar(
                "SELECT COUNT(*) FROM (SELECT DISTINCT match_id, COALESCE(chest_id, -id) FROM chest_events)")
            s.total_tokens = self._scalar("SELECT COUNT(*) FROM token_events")
            last = self.conn.execute("SELECT total_chests_at FROM token_events ORDER BY ts DESC LIMIT 1").fetchone()
            s.since_last_token = s.total_chests - (last["total_chests_at"] if last else 0)
            s.today_chests = self._scalar(
                "SELECT COUNT(*) FROM chest_events WHERE date(ts,'unixepoch','localtime') = date(?,'unixepoch','localtime')",
                (now,),
            )
            lm = self.conn.execute(
                "SELECT chests, started_at, placement FROM matches WHERE ok=1 ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if lm:
                s.last_match_chests, s.last_match_at, s.last_match_placement = lm["chests"], lm["started_at"], lm["placement"]
            s.best_match = self._scalar("SELECT MAX(chests) FROM matches WHERE ok=1")
            s.best_day = self._scalar(
                "SELECT MAX(c) FROM (SELECT COUNT(*) c FROM chest_events GROUP BY date(ts,'unixepoch','localtime'))"
            )
            row = self.conn.execute(
                "SELECT MIN(chests_since_previous) FROM token_events WHERE chests_since_previous > 0"
            ).fetchone()
            s.fewest_chests_for_token = row[0] if row and row[0] is not None else None
            row = self.conn.execute("SELECT SUM(duration), COUNT(*) FROM matches WHERE ok=1").fetchone()
            s.tracked_seconds = float(row[0] or 0.0)
            s.matches_count = int(row[1] or 0)
            s.distinct_items = self._scalar("SELECT COUNT(DISTINCT item) FROM items")
        return s

    def matches(self, limit: int = 1000) -> list[MatchRow]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT m.*, (SELECT COUNT(*) FROM token_events t WHERE t.match_id=m.id) AS tokens,
                          (SELECT COUNT(*) FROM chest_events c WHERE c.match_id=m.id AND c.how='cassé') AS broken,
                          (SELECT COUNT(*) FROM chest_events c WHERE c.match_id=m.id AND c.special=1) AS special,
                          (SELECT COUNT(*) FROM chest_events c WHERE c.match_id=m.id AND c.reopen=1) AS reopens,
                          (SELECT COUNT(DISTINCT COALESCE(c.chest_id, -c.id)) FROM chest_events c WHERE c.match_id=m.id)
                              AS unique_chests
                   FROM matches m ORDER BY m.started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            try:
                warns = json.loads(r["warnings"] or "[]")
            except json.JSONDecodeError:
                warns = []
            out.append(MatchRow(r["id"], r["started_at"], r["duration"], r["chests"], r["broken"], r["special"],
                                r["reopens"], r["unique_chests"],
                                r["tokens"], r["placement"],
                                r["total_players"], r["eliminations"], r["playlist"], bool(r["ok"]), r["error"],
                                warns, r["replay_path"], json.loads(r["diagnostics"] or "{}")))
        return out

    def last_match_id(self) -> int | None:
        with self._lock:
            row = self.conn.execute("SELECT id FROM matches WHERE ok=1 ORDER BY started_at DESC LIMIT 1").fetchone()
        return row["id"] if row else None

    def item_totals(self) -> list[sqlite3.Row]:
        """Objets obtenus : nombre de fois, quantité totale, première et dernière fois."""
        with self._lock:
            return self.conn.execute(
                """SELECT item, COUNT(*) AS times, SUM(count) AS quantity, MIN(ts) AS first_ts, MAX(ts) AS last_ts,
                          COUNT(DISTINCT match_id) AS matches
                   FROM items GROUP BY item ORDER BY times DESC"""
            ).fetchall()

    def match_items(self, match_id: int) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM items WHERE match_id=? ORDER BY ts", (match_id,)).fetchall()

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
        base = self.initial_chests
        pts = [(rows[i]["ts"], base + i + 1) for i in range(0, n, step)]
        if pts[-1][1] != base + n:
            pts.append((rows[-1]["ts"], base + n))
        return pts

    def tokens(self) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM token_events ORDER BY ts DESC").fetchall()

    def level_history(self, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute("SELECT * FROM level_events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", (key, value))
            self.conn.commit()

    # ------------------------------------------------------------------ maintenance
    def reset(self) -> None:
        with self._lock:
            self.conn.executescript(
                "DELETE FROM chest_events; DELETE FROM items; DELETE FROM token_events; DELETE FROM level_events;"
                "DELETE FROM matches; DELETE FROM meta WHERE key='initial_chests';"
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
        check = sqlite3.connect(str(src))
        try:
            check.execute("SELECT COUNT(*) FROM matches").fetchone()
        finally:
            check.close()
        with self._lock:
            src_conn = sqlite3.connect(str(src))
            src_conn.backup(self.conn)
            src_conn.close()
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def export_json(self, dest: Path) -> Path:
        with self._lock:
            payload = {"exported_at": datetime.now().isoformat(timespec="seconds")}
            for t in ("matches", "chest_events", "items", "token_events", "level_events"):
                payload[t] = [dict(r) for r in self.conn.execute(f"SELECT * FROM {t}")]
        Path(dest).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return Path(dest)

    def export_csv(self, dest: Path) -> Path:
        rows = self.matches(limit=1_000_000)
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["partie", "date", "duree_min", "mode", "classement", "joueurs", "eliminations",
                        "coffres", "replay"])
            for r in rows:
                w.writerow([r.id, datetime.fromtimestamp(r.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                            round(r.duration / 60, 1), r.playlist or "", r.placement or "", r.total_players or "",
                            r.eliminations if r.eliminations is not None else "", r.chests,
                            Path(r.replay_path).name])
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
