"""Journal d'analyse : pour chaque replay, un fichier texte qui explique ce qui a été compté et pourquoi.

Écrit dans ``%APPDATA%\\PirateTracker\\logs\\``. Sert à comprendre un comptage surprenant (nouvelle
saison, coffre non reconnu…) sans avoir à transmettre le replay lui-même.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .paths import data_dir


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def format_report(res: dict, version: str = "") -> str:
    chests = res.get("chests") or []
    broken = res.get("broken_count", sum(1 for c in chests if c.get("how") == "cassé"))
    reopens = res.get("reopen_count", sum(1 for c in chests if c.get("reopen")))
    lines = [
        f"Pirate Tracker {version} · lecteur {res.get('reader_version', '?')} · analysé le {datetime.now():%d/%m/%Y %H:%M}",
        f"Replay : {Path(res.get('file', '')).name}",
        f"Fortnite : {res.get('branch', '?')} · mode : {res.get('playlist') or '?'} · durée : "
        f"{int(float(res.get('duration_s') or 0) // 60)} min",
        "",
        f"OUVERTURES COMPTÉES : {res.get('total_openings', len(chests))}"
        f"  (coffres uniques : {res.get('unique_chests', '?')}, réouvertures : {reopens}, cassés : {broken},"
        f" ouvreur déduit : {res.get('inferred_openings', 0)})",
        f"Coffres par classe : {res.get('chest_classes_opened') or {}}",
        f"Autres conteneurs fouillés (NON comptés) : {res.get('other_containers_searched') or {}}",
        f"Coffres détruits sans auteur connu (NON comptés) : {res.get('chests_destroyed_unattributed', '?')}",
        "",
        f"Joueur identifié : {res.get('owner_found')} · ses personnages : {res.get('owner_pawn_ids')}"
        f" · personnages dans la partie : {res.get('pawns_seen')}",
        f"Coffres vus : {res.get('chests_seen')} · ouverts par quelqu'un : {res.get('chests_opened_by_anyone')}"
        f" · avec ouvreur connu : {res.get('chest_searches_seen')}",
        f"Replay incomplet : {bool(res.get('partial'))} · analyse réussie : {bool(res.get('ok'))}",
    ]
    if res.get("error"):
        lines.append(f"Erreur : {res['error']}")
    if res.get("warnings"):
        lines += ["", "AVERTISSEMENTS"] + [f"- {w}" for w in res["warnings"]]
    if res.get("class_decisions"):
        lines += ["", "CLASSES ET RÔLE ATTRIBUÉ (preuve)"] + [f"- {k} : {v}" for k, v in res["class_decisions"].items()]
    if res.get("decisions"):
        lines += ["", "JOURNAL DES COFFRES (moi ou mes coffres)"] + [f"- {d}" for d in res["decisions"]]
    return "\n".join(lines)


def write_log(res: dict, version: str = "") -> Path | None:
    name = Path(res.get("file") or "replay").stem
    safe = re.sub(r"[^\w.-]+", "_", name)[:120] or "replay"
    path = logs_dir() / f"{safe}.txt"
    try:
        path.write_text(format_report(res, version), encoding="utf-8")
        return path
    except OSError:
        return None
