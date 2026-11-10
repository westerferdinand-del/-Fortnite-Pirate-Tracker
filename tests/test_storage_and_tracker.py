"""Base de données, persistance, niveaux, records, jetons."""
import json

import pytest

from pirate_tracker import levels
from pirate_tracker.config import Config
from pirate_tracker.database import Database
from pirate_tracker.tracker import Tracker


def fake_result(path="C:/Demos/a.replay", chests=3, items=(), ok=True, started="2026-11-01T20:00:00", **kw):
    return {"ok": ok, "file": path, "started_utc": started, "duration_s": 1200.0, "placement": 5,
            "total_players": 100, "eliminations": 2, "playlist": "Playlist_DefaultSolo",
            "chests": [{"t": 60.0 + i * 30, "id": 1000 + i, "kind": "Chest"} for i in range(chests)],
            "items": [{"t": 100.0 + i, "item": it, "count": 1} for i, it in enumerate(items)], **kw}


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    yield d
    d.close()


@pytest.fixture
def tracker(db, tmp_path):
    return Tracker(db, Config(tmp_path / "settings.json"))


def test_levels_computation():
    t = [10, 25, 50, 100, 200]
    st = levels.compute_level(30, t)
    assert (st.level, st.stars, st.next_star_at, st.prev_star_at) == (1, 2, 50, 25)
    assert levels.compute_level(200, t).level == 2
    assert levels.transitions(9, 10, t)[0][0] == "star"
    assert levels.transitions(199, 200, t)[0][0] == "level"
    with pytest.raises(ValueError):
        levels.validate_thresholds([5, 4, 3, 2, 1])


def test_match_is_recorded_and_persists(tmp_path):
    db = Database(tmp_path / "p.db")
    tr = Tracker(db, Config(tmp_path / "s.json"))
    events = []
    tr.subscribe(lambda k, p: events.append(k))
    tr.record_match(fake_result(chests=12, items=["WID_Assault_CoreAR_Athena_UC"]), size=10, mtime=1.0)
    s = tr.stats()
    assert (s.total_chests, s.last_match_chests, s.matches_count) == (12, 12, 1)
    assert "match" in events and "star" in events
    db.close()
    db2 = Database(tmp_path / "p.db")  # redémarrage de l'application
    assert db2.stats().total_chests == 12
    assert db2.is_processed("C:/Demos/a.replay", 10, 1.0)
    assert not db2.is_processed("C:/Demos/a.replay", 11, 1.0)  # le fichier a changé → à relire
    db2.close()


def test_reprocessing_same_replay_never_double_counts(tracker):
    tracker.record_match(fake_result(chests=4), size=1, mtime=1)
    p = tracker.record_match(fake_result(chests=5), size=2, mtime=2)  # même replay, relu après sa fin
    assert p["replaced"] and p["delta"] == 1
    assert tracker.stats().total_chests == 5 and tracker.stats().matches_count == 1


def test_failed_replay_counts_nothing(tracker):
    tracker.record_match({"ok": False, "file": "x.replay", "error": "boom"})
    assert tracker.stats().total_chests == 0
    assert tracker.db.matches()[0].ok is False


def test_token_found_from_items_and_since_counter(tracker):
    got = []
    tracker.subscribe(lambda k, p: got.append((k, p)))
    tracker.record_match(fake_result("a.replay", chests=7, started="2026-11-01T20:00:00"))
    tracker.record_match(fake_result("b.replay", chests=3, items=["Athena_PirateToken_Item"],
                                     started="2026-11-02T20:00:00"))
    toks = [p for k, p in got if k == "token"]
    # Coffres de la partie b à t=60, 90, 120 s ; jeton ramassé à t=100 s → 7 + 2 coffres avant le jeton
    assert len(toks) == 1 and toks[0]["chests_since_previous"] == 9
    tracker.record_match(fake_result("c.replay", chests=2, started="2026-11-03T20:00:00"))
    s = tracker.stats()
    assert (s.total_tokens, s.since_last_token) == (1, 3)  # 1 coffre après le jeton (b) + 2 (c)


def test_user_can_designate_the_token_item(tracker):
    tracker.record_match(fake_result("a.replay", chests=4, items=["Some_Unknown_Coin_Item"]))
    assert tracker.stats().total_tokens == 0
    tracker.mark_token_item("Some_Unknown_Coin_Item", True)
    assert tracker.stats().total_tokens == 1
    tracker.mark_token_item("Some_Unknown_Coin_Item", False)
    assert tracker.stats().total_tokens == 0


def test_record_event_when_best_match_beaten(tracker):
    got = []
    tracker.subscribe(lambda k, p: got.append(k))
    tracker.record_match(fake_result("a.replay", chests=3))
    tracker.record_match(fake_result("b.replay", chests=5))
    assert got.count("record") == 1


def test_import_is_silent_but_counts(tracker):
    got = []
    tracker.subscribe(lambda k, p: got.append(k))
    gained = tracker.import_results([fake_result(f"{i}.replay", chests=4) for i in range(3)])
    assert gained == 12 and "imported" in got and "record" not in got


def test_history_rewards_export_backup_restore(tracker, tmp_path):
    db = tracker.db
    tracker.record_match(fake_result("a.replay", chests=2, items=["WID_Shotgun_X_Athena_SR", "AthenaAmmoDataShells"]))
    tracker.record_match(fake_result("b.replay", chests=1, items=["WID_Shotgun_X_Athena_SR"]))
    rows = {r["item"]: r for r in db.item_totals()}
    assert rows["WID_Shotgun_X_Athena_SR"]["times"] == 2 and rows["WID_Shotgun_X_Athena_SR"]["matches"] == 2
    db.export_json(tmp_path / "e.json")
    assert len(json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))["matches"]) == 2
    db.export_csv(tmp_path / "e.csv")
    assert "coffres" in (tmp_path / "e.csv").read_text(encoding="utf-8-sig")
    db.backup(tmp_path / "b.db")
    tracker.reset_all()
    assert db.total_chests() == 0
    db.restore(tmp_path / "b.db")
    assert db.total_chests() == 3


def test_delete_match(tracker):
    tracker.record_match(fake_result("a.replay", chests=2))
    tracker.delete_match(tracker.db.matches()[0].id)
    assert tracker.stats().total_chests == 0


def test_v1_database_is_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE sessions(id INTEGER PRIMARY KEY, started_at REAL, ended_at REAL, last_seen REAL);"
                    "CREATE TABLE chest_events(id INTEGER PRIMARY KEY, session_id INT, ts REAL, confidence REAL, method TEXT);"
                    "INSERT INTO chest_events(session_id, ts) VALUES (1, 1.0);")
    c.commit()
    c.close()
    db = Database(path)
    assert db.total_chests() == 0  # anciennes données mises de côté (tables v1_*)
    assert db.conn.execute("SELECT COUNT(*) FROM v1_chest_events").fetchone()[0] == 1
    db.close()


def test_config_roundtrip(tmp_path):
    c = Config(tmp_path / "c.json")
    c.set("overlay", "opacity", 0.5)
    c2 = Config(tmp_path / "c.json")
    assert c2.get("overlay", "opacity") == 0.5
    assert c2.get("replays", "enabled") is True
