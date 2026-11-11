"""Petit serveur HTTP (thread) : page de l'application compagnon + API JSON des statistiques.

Sécurité : l'accès exige une clé secrète aléatoire (dans le QR code / l'adresse), comparée en temps
constant. Lecture seule : l'API ne permet aucune modification.
"""
from __future__ import annotations

import hmac
import json
import secrets
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import __version__
from .. import items as items_mod
from ..paths import resource_path

WEB_DIR = resource_path("companion", "web")


def local_ip() -> str:
    """Adresse IP de l'ordinateur sur le réseau local (aucune donnée n'est envoyée)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def new_token() -> str:
    return secrets.token_urlsafe(12)


def build_summary(tracker, recording: bool = False) -> dict:
    """Toutes les données affichées par l'application compagnon."""
    db = tracker.db
    s = tracker.stats()
    st = tracker.level()
    matches = db.matches(30)
    counts = dict(db.daily_counts(30))
    today = datetime.now().date()
    days = []
    for i in range(29, -1, -1):
        d = datetime.fromordinal(today.toordinal() - i).date()
        days.append({"date": d.isoformat(), "count": counts.get(d.isoformat(), 0)})
    is_token = tracker.token_matcher()
    loot = []
    for r in db.item_totals():
        info = items_mod.describe(r["item"])
        if info.category in ("munitions", "matériaux"):
            continue
        loot.append({"name": info.name, "rarity": info.rarity, "times": r["times"], "token": is_token(r["item"])})
    order = ["Mythique", "Légendaire", "Épique", "Rare", "Peu commun", "Commun", ""]
    loot.sort(key=lambda x: (not x["token"], order.index(x["rarity"]) if x["rarity"] in order else 6, -x["times"]))
    counted = s.total_chests - s.initial_chests
    o = tracker.odds()
    return {
        "recording": recording,
        "odds": {"one_in": o.one_in, "percent": o.percent, "half_at": o.openings_for_half},
        "version": __version__,
        "generated_at": time.time(),
        "total": s.total_chests,
        "counted": counted,
        "initial": s.initial_chests,
        "unique": s.unique_chests,
        "reopens": s.total_reopens,
        "broken": s.total_broken,
        "today": s.today_chests,
        "since_token": s.since_last_token,
        "best_match": s.best_match,
        "best_day": s.best_day,
        "matches_count": s.matches_count,
        "avg": round(counted / s.matches_count, 1) if s.matches_count else 0,
        "play_seconds": s.tracked_seconds,
        "level": {"level": st.level, "steps_done": st.stars, "progress": st.star_progress,
                  "remaining": st.next_star_at - st.chests_in_level},
        "last_match": None if s.last_match_chests is None else {
            "chests": s.last_match_chests, "at": s.last_match_at, "placement": s.last_match_placement},
        "days": days,
        "matches": [{"at": m.started_at, "duration": m.duration, "chests": m.chests, "unique": m.unique_chests,
                     "broken": m.broken, "placement": m.placement, "players": m.total_players,
                     "kills": m.eliminations, "mode": _mode(m.playlist), "ok": m.ok} for m in matches],
        "loot": loot[:60],
    }


def _mode(p: str | None) -> str:
    if not p:
        return "Partie"
    low = p.lower()
    team = ("Solo" if "solo" in low else "Duo" if "duo" in low else "Trio" if "trio" in low else
            "Escouade" if "squad" in low else "")
    mode = "Zéro construction" if "nobuild" in low else ("Battle Royale" if team else "")
    return " · ".join(x for x in (mode, team) if x) or p.replace("Playlist_", "").replace("_", " ")


class CompanionServer:
    def __init__(self, tracker, token: str, port: int = 8765, recording=None):
        self.tracker = tracker
        self.recording = recording or (lambda: False)
        self.token = token
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def url(self) -> str:
        return f"http://{local_ip()}:{self.port}/?t={self.token}"

    def start(self) -> bool:
        if self._httpd:
            return True
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # pas de journal console
                pass

            def _authorized(self) -> bool:
                q = parse_qs(urlparse(self.path).query)
                given = (q.get("t") or [""])[0] or self.headers.get("X-Token", "")
                cookie = self.headers.get("Cookie", "")
                for part in cookie.split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == "pt" and v:
                        given = given or v
                return bool(given) and hmac.compare_digest(given, server.token)

            def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                if path in ("/manifest.webmanifest", "/icon.png", "/icon-180.png"):
                    f = WEB_DIR / path.lstrip("/")
                    ctype = "application/manifest+json" if path.endswith("webmanifest") else "image/png"
                    if f.exists():
                        return self._send(200, f.read_bytes(), ctype)
                    return self._send(404, b"", "text/plain")
                if not self._authorized():
                    msg = ("Accès refusé : ouvrez l'adresse complète affichée dans Pirate Tracker "
                           "(Réglages → Application mobile).").encode()
                    return self._send(403, msg, "text/plain; charset=utf-8")
                if path in ("/", "/index.html"):
                    body = (WEB_DIR / "index.html").read_bytes()
                    # Cookie : la page ajoutée à l'écran d'accueil reste autorisée sans la clé dans l'adresse
                    return self._send(200, body, "text/html; charset=utf-8",
                                      {"Set-Cookie": f"pt={server.token}; Max-Age=31536000; Path=/; SameSite=Strict"})
                if path == "/api/summary":
                    try:
                        data = build_summary(server.tracker, bool(server.recording()))
                    except Exception as e:  # noqa: BLE001
                        return self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
                    return self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                      "application/json; charset=utf-8")
                return self._send(404, b"", "text/plain")

        try:
            self._httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError as e:
            self.error = f"Port {self.port} indisponible : {e}"
            self._httpd = None
            return False
        self.error = None
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="companion", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


__all__ = ["CompanionServer", "local_ip", "new_token", "build_summary"]
