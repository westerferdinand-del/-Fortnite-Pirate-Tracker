"""Lecteur de replays (sur un vrai replay Fortnite), surveillance du dossier, noms d'objets, interface."""
import os
import shutil
from pathlib import Path

import pytest

from pirate_tracker import items, replays

DATA = Path(__file__).parent / "data"
SAMPLE = DATA / "chapter5season5.replay"  # replay réel (Fortnite v32.00, nov. 2024), cf. README


def reader_available() -> bool:
    try:
        replays.find_reader()
        return True
    except replays.ReaderNotFound:
        return False


needs_reader = pytest.mark.skipif(not (SAMPLE.exists() and reader_available()),
                                  reason="replay d'exemple ou lecteur de replays absent")


@needs_reader
def test_real_replay_owner_chests():
    """Vrai replay du Chapitre 5 : coffres ouverts par le joueur qui a enregistré le replay.

    Valeur de référence établie en inspectant le replay : 5 ouvertures dont SearchingPawn est le
    personnage du propriétaire (dont 2 coffres détruits après ouverture, sans bAlreadySearched).
    """
    res = replays.read_replay(SAMPLE)
    assert res["ok"], res.get("error")
    assert res["owner_found"]
    assert [c["t"] for c in res["chests"]] == pytest.approx([91.1, 105.5, 161.2, 232.5, 377.4], abs=0.05)
    assert len({c["id"] for c in res["chests"]}) == 5
    assert res["chests_opened_by_anyone"] > len(res["chests"])  # les coffres des autres ne sont pas comptés
    assert res["placement"] == 2 and res["eliminations"] == 8
    assert res["started_utc"].startswith("2024-11-03")
    assert not res["is_live"] and res["unknown_chest_classes"] == []
    picked = {i["item"] for i in res["items"]}
    assert "WID_Assault_CoreAR_Athena_UC" in picked and "Athena_WadsItemData" in picked


@needs_reader
def test_unreadable_and_missing_files(tmp_path):
    bad = tmp_path / "bad.replay"
    bad.write_bytes(b"not a replay" * 100)
    res = replays.read_replays([bad, tmp_path / "missing.replay"])
    assert [r["ok"] for r in res] == [False, False]


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0


def make_watcher(demos: Path, processed: dict, results: list, reader, since=0.0):
    return replays.ReplayWatcher(
        demos_dir=lambda: demos,
        is_processed=lambda p, s, m: processed.get(p) == (s, m),
        on_result=results.append,
        since=lambda: since,
        stable_seconds=30,
        reader=reader,
    )


def test_watcher_waits_until_replay_is_finished(tmp_path):
    demos = tmp_path / "Demos"
    demos.mkdir()
    f = demos / "UnsavedReplay-2026.11.10-20.00.00.replay"
    f.write_bytes(b"x" * 100)
    os.utime(f, (1_000_000, 1_000_000))
    calls = []

    def reader(paths):
        calls.append(paths)
        return [{"ok": True, "file": p, "is_live": False, "chests": []} for p in paths]

    results = []
    w = make_watcher(demos, {}, results, reader)
    assert w.scan(1_000_005) == []  # vu pour la première fois
    f.write_bytes(b"x" * 200)  # la partie continue, le fichier grossit
    os.utime(f, (1_000_020, 1_000_020))
    assert w.scan(1_000_025) == []
    assert w.scan(1_000_040) == []  # pas encore 30 s sans changement
    out = w.scan(1_000_060)
    assert len(out) == 1 and calls == [[str(f)]] and out[0]["_size"] == 200


def test_watcher_skips_live_replay_and_old_ones(tmp_path):
    demos = tmp_path / "Demos"
    demos.mkdir()
    live = demos / "live.replay"
    live.write_bytes(b"x")
    os.utime(live, (1_000_000, 1_000_000))
    old = demos / "old.replay"
    old.write_bytes(b"y")
    os.utime(old, (10, 10))
    results = []
    w = make_watcher(demos, {}, results, lambda ps: [{"ok": True, "file": p, "is_live": True} for p in ps],
                     since=500_000)
    w.scan(1_000_001)
    assert w.scan(1_000_100) == [] and results == []  # enregistrement en cours : rien n'est compté


def test_watcher_ignores_already_processed(tmp_path):
    demos = tmp_path / "Demos"
    demos.mkdir()
    f = demos / "a.replay"
    f.write_bytes(b"x" * 10)
    st = f.stat()
    results = []
    w = make_watcher(demos, {str(f): (st.st_size, st.st_mtime)}, results,
                     lambda ps: pytest.fail("ne doit pas relire un replay déjà compté"))
    w.scan(st.st_mtime + 100)
    w.scan(st.st_mtime + 200)
    assert results == []


def test_watcher_reports_missing_folder(tmp_path):
    w = make_watcher(tmp_path / "nope", {}, [], lambda ps: [])
    w.scan()
    assert w.status.level == "configuring" and "replays" in w.status.message


def test_item_names():
    i = items.describe("WID_Assault_CoreAR_Athena_UC")
    assert (i.name, i.rarity, i.category) == ("Fusil d'assaut peu commun", "Peu commun", "arme")
    assert items.describe("Athena_WadsItemData").name == "Lingots d'or"
    assert items.describe("AthenaAmmoDataShells").category == "munitions"
    assert items.describe("WID_Hook_Gun_VR_Ore_T03").rarity == "Épique"
    pats = items.DEFAULT_TOKEN_PATTERNS
    assert items.is_token("Athena_PirateToken", pats, [])
    assert items.is_token("WID_Pirate_Coin_Collectible", pats, [])
    assert not items.is_token("WID_Pirate_Cannon", pats, [])  # « pirate » seul ne suffit pas
    assert items.is_token("Anything", pats, ["Anything"])


def test_ui_smoke(tmp_path, monkeypatch):
    """Construit l'application complète (sans écran) et vérifie la mise à jour en fin de partie."""
    monkeypatch.setenv("PIRATE_TRACKER_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from pirate_tracker.app import AppContext
    from tests.test_storage_and_tracker import fake_result

    ctx = AppContext(app, start_watcher=False)
    try:
        ctx.bridge.replay_result.emit(fake_result("a.replay", chests=11, items=["WID_Assault_CoreAR_Athena_SR"]))
        app.processEvents()
        assert ctx.overlay.chests == 11  # le widget n'affiche que le total de coffres
        ctx.bridge.replay_result.emit(fake_result("b.replay", chests=2, items=["Athena_PirateToken"],
                                                  started="2026-11-02T10:00:00"))
        app.processEvents()
        assert ctx.overlay.chests == 13
        assert ctx.tracker.stats().since_last_token == 0  # le jeton reste détecté (célébration)
        for key in ctx.window.pages:
            ctx.window.show_page(key)
            app.processEvents()
        assert ctx.window.pages["dashboard"].hero.big.text() == "013"
        assert ctx.window.pages["history"].table.rowCount() == 2
        assert ctx.window.pages["rewards"].table.rowCount() >= 1
    finally:
        ctx.quit()


@needs_reader
def test_end_to_end_real_replay_through_watcher(tmp_path):
    """Un vrai replay déposé dans le dossier → analysé une fois terminé → 5 coffres en base."""
    from pirate_tracker.config import Config
    from pirate_tracker.database import Database
    from pirate_tracker.tracker import Tracker

    demos = tmp_path / "Demos"
    demos.mkdir()
    dst = demos / SAMPLE.name
    shutil.copy(SAMPLE, dst)
    db = Database(tmp_path / "db.db")
    tr = Tracker(db, Config(tmp_path / "s.json"))
    w = replays.ReplayWatcher(lambda: demos, db.is_processed, tr.record_match, stable_seconds=30)
    st = dst.stat()
    w.scan(st.st_mtime + 1)
    w.scan(st.st_mtime + 60)
    assert db.stats().total_chests == 5
    w.scan(st.st_mtime + 120)  # déjà compté : aucun double comptage
    assert db.stats().total_chests == 5 and db.stats().matches_count == 1
    db.close()
