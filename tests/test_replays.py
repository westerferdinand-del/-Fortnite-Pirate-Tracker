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

    Valeur de référence établie en inspectant le replay : 5 coffres dont SearchingPawn est le
    personnage du propriétaire : 3 ouverts (bAlreadySearched) et 2 cassés (vie à 0, bDestroyed).
    """
    res = replays.read_replay(SAMPLE)
    assert res["ok"], res.get("error")
    assert res["owner_found"]
    assert [c["t"] for c in res["chests"]] == pytest.approx([91.1, 105.5, 161.2, 232.5, 377.4], abs=0.05)
    assert len({c["id"] for c in res["chests"]}) == 5
    assert res["chests_opened_by_anyone"] > len(res["chests"])  # les coffres des autres ne sont pas comptés
    assert res["placement"] == 2 and res["eliminations"] == 8
    assert res["started_utc"].startswith("2024-11-03")
    assert [c["how"] for c in res["chests"]] == ["cassé", "ouvert", "cassé", "ouvert", "ouvert"]
    assert not any(c["special"] for c in res["chests"])
    assert not res["is_live"]
    # Classes de coffres non standard présentes dans la partie, lues automatiquement (alias générique)
    assert any("Tiered_Chest_6_Parent" in p for p in res["special_chest_classes"])
    assert any("FactionChest_Generic_Parent" in p for p in res["special_chest_classes"])
    assert res["chests_seen"] == 95
    picked = {i["item"] for i in res["items"]}
    assert "WID_Assault_CoreAR_Athena_UC" in picked and "Athena_WadsItemData" in picked


@needs_reader
def test_cut_replay_keeps_chests_read_before_the_cut(tmp_path):
    """Partie quittée brutalement / jeu fermé : le replay est coupé, les coffres déjà lus sont gardés."""
    data = SAMPLE.read_bytes()
    cut = tmp_path / "coupe.replay"
    cut.write_bytes(data[: int(len(data) * 0.7)])  # avant correction : erreur → 0 coffre
    res = replays.read_replay(cut)
    assert res["ok"] and res["partial"]
    assert len(res["chests"]) == 5
    assert any("incomplet" in w for w in res["warnings"])


@needs_reader
def test_diagnostics_are_reported():
    res = replays.read_replay(SAMPLE)
    assert (res["pawns_seen"], res["owner_pawns"]) == (143, 2)
    assert res["chest_searches_seen"] >= 50
    assert res["warnings"] == []


@needs_reader
def test_unique_chests_and_openings_on_real_replay(tmp_path):
    """Non-régression Chapitre 5 : 5 ouvertures = 5 coffres uniques, aucune déduite, journal écrit."""
    res = replays.read_replay(SAMPLE)
    assert (res["total_openings"], res["unique_chests"], res["inferred_openings"]) == (5, 5, 0)
    assert all(c["direct"] and not c["reopen"] for c in res["chests"])
    assert res["class_decisions"]["Tiered_Chest_Athena"].startswith("coffre")
    assert res["class_decisions"]["Tiered_Ammo_Athena"].startswith("autre conteneur")
    assert len(res["decisions"]) == 5 and all("COMPTÉ" in d for d in res["decisions"])


@pytest.mark.skipif(not reader_available(), reason="lecteur de replays absent")
def test_reader_selftest_refills_and_reopenings():
    """Scénarios simulés : réouverture d'un coffre rempli (même joueur ou autre), coffre déjà ouvert, cassé…"""
    import subprocess

    out = subprocess.run(replays.find_reader() + ["--selftest"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "selftest OK" in out.stdout


def test_chest_categories_and_pirate_shop_token():
    assert items.chest_category("Tiered_Chest_Athena") == ("standard", False)
    assert items.chest_category("B_TreasureHunt_Chest_Season") == ("trésor", False)  # coffre normal de la saison
    assert items.chest_category("Tiered_Chest_Rare_Athena") == ("rare", True)
    assert items.chest_category("BuriedChest_Parent") == ("enterré", True)
    assert items.chest_category("Tiered_Chest_6_Parent") == ("standard", False)
    pats = items.DEFAULT_TOKEN_PATTERNS
    assert items.is_token("ID_PirateShop_Access_Token", pats, [])
    assert items.is_token("Athena_PirateShopAccess", pats, [])


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
        assert ctx.window.pages["overview"].total.text() == "13"
        assert ctx.window.pages["overview"].recent.rowCount() == 2
        assert ctx.window.pages["matches"].table.rowCount() == 2
        assert ctx.window.pages["loot"].table.rowCount() >= 1
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


@needs_reader
def test_diagnostic_text_for_a_real_match(tmp_path, monkeypatch):
    """Le diagnostic copiable liste les coffres par classe et les autres conteneurs fouillés."""
    monkeypatch.setenv("PIRATE_TRACKER_HOME", str(tmp_path))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from pirate_tracker.app import AppContext

    ctx = AppContext(app, start_watcher=False)
    try:
        res = replays.read_replay(SAMPLE)
        ctx.tracker.record_match(res, size=1, mtime=1.0)
        page = ctx.window.pages["matches"]
        page.refresh()
        text = page.diagnostic_text(ctx.tracker.db.matches()[0])
        print(text)
        assert "OUVERTURES COMPTÉES : 5  (coffres uniques : 5, réouvertures : 0, cassés : 2" in text
        assert "Tiered_Ammo_Athena : autre conteneur" in text  # rôle de chaque classe, avec la preuve
        assert "cassé par moi → COMPTÉ" in text and "ouverture par moi → COMPTÉ" in text  # journal par coffre
        assert "'Tiered_Chest_Athena': 5" in text
        assert "'Tiered_Ammo_Athena': 8" in text  # caisses de munitions : vues mais pas comptées
        assert "++Fortnite+Release-32.00" in text
    finally:
        ctx.quit()


# ---------------------------------------------------------------- en-tête (fin de partie immédiate)
def make_live_copy(src: Path, dst: Path) -> None:
    """Copie du vrai replay telle qu'elle est PENDANT la partie : « en direct » et sans clé de chiffrement."""
    import struct

    data = bytearray(src.read_bytes())
    pos = 8
    count = struct.unpack_from("<i", data, pos)[0]
    pos += 4 + count * 20 + 12
    n = struct.unpack_from("<i", data, pos)[0]
    pos += 4 + (n if n >= 0 else -2 * n)
    struct.pack_into("<I", data, pos, 1)  # bIsLive = 1
    key_size_pos = pos + 4 + 8 + 4 + 4
    size = struct.unpack_from("<I", data, key_size_pos)[0]
    struct.pack_into("<I", data, key_size_pos, 0)  # pas encore de clé
    del data[key_size_pos + 4:key_size_pos + 4 + size]
    dst.write_bytes(bytes(data))


@pytest.mark.skipif(not SAMPLE.exists(), reason="replay d'exemple absent")
def test_header_of_real_replay(tmp_path):
    from pirate_tracker.replay_header import read_header

    h = read_header(SAMPLE)
    assert (h.length_ms, h.is_live, h.is_encrypted, h.has_key, h.finished) == (900374, False, True, True, True)
    live = tmp_path / "live.replay"
    make_live_copy(SAMPLE, live)
    hl = read_header(live)
    assert hl.is_live and not hl.has_key and not hl.finished
    assert read_header(tmp_path / "absent.replay") is None
    (tmp_path / "bad.replay").write_bytes(b"\x00" * 50)
    assert read_header(tmp_path / "bad.replay") is None


@needs_reader
def test_recording_replay_is_never_read_nor_counted_as_failure(tmp_path):
    """Bug corrigé : un replay en cours (fichier immobile 30 s en pleine partie) donnait un faux « échec »."""
    demos = tmp_path / "Demos"
    demos.mkdir()
    live = demos / "UnsavedReplay-live.replay"
    make_live_copy(SAMPLE, live)
    calls = []
    w = make_watcher(demos, {}, [], lambda ps: calls.append(ps) or [])
    st = live.stat()
    for dt in (1, 40, 120, 600):
        assert w.scan(st.st_mtime + dt) == []
    assert calls == [] and w.status.recording == [live.name]
    assert "Partie en cours" in w.status.message


@needs_reader
def test_finished_replay_is_read_within_seconds(tmp_path):
    """En-tête « terminé » : lecture 3 s après la dernière écriture (au lieu de 30 s)."""
    demos = tmp_path / "Demos"
    demos.mkdir()
    dst = demos / "UnsavedReplay-fin.replay"
    shutil.copy(SAMPLE, dst)
    st = dst.stat()
    results = []
    w = replays.ReplayWatcher(lambda: demos, lambda *a: False, results.append, stable_seconds=30)
    w.scan(st.st_mtime + 0.5)
    assert results == []
    w.scan(st.st_mtime + 4)
    assert len(results) == 1 and len(results[0]["chests"]) == 5
