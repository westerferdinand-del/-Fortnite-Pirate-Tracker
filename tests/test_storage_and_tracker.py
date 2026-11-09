"""Base de données, persistance, niveaux, records et tracker."""
import json
import time

import pytest

from pirate_tracker import levels
from pirate_tracker.config import Config
from pirate_tracker.database import Database
from pirate_tracker.tracker import Tracker


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
    assert levels.compute_level(0, t).level == 1 and levels.compute_level(0, t).stars == 0
    st = levels.compute_level(30, t)
    assert (st.level, st.stars, st.next_star_at, st.prev_star_at) == (1, 2, 50, 25)
    assert abs(st.star_progress - 0.2) < 1e-9
    assert levels.compute_level(200, t).level == 2
    assert levels.compute_level(210, t).stars == 1
    ev = levels.transitions(9, 10, t)
    assert ev and ev[0][0] == "star"
    assert levels.transitions(199, 200, t)[0][0] == "level"
    with pytest.raises(ValueError):
        levels.validate_thresholds([5, 4, 3, 2, 1])


def test_tracker_counts_and_persists(tmp_path):
    cfg = Config(tmp_path / "s.json")
    db = Database(tmp_path / "p.db")
    tr = Tracker(db, cfg)
    events = []
    tr.subscribe(lambda k, p: events.append(k))
    tr.on_fortnite(True)
    for _ in range(12):
        tr.record_chest(0.9, "prompt+burst")
    assert tr.stats().total_chests == 12 and tr.stats().session_chests == 12
    assert "star" in events
    tok = tr.record_token(0.95)
    assert tok["chests_since_previous"] == 12
    tr.record_chest()
    assert tr.stats().since_last_token == 1
    db.close()  # simulation d'une fermeture brutale (session non terminée)

    db2 = Database(tmp_path / "p.db")  # redémarrage
    s = db2.stats()
    assert (s.total_chests, s.total_tokens, s.since_last_token) == (13, 1, 1)
    assert db2.sessions()[0].ended_at is not None  # session pendante refermée
    db2.close()


def test_record_event(tracker):
    got = []
    tracker.subscribe(lambda k, p: got.append(k))
    tracker.start_session()
    for _ in range(3):
        tracker.record_chest()
    tracker.end_session()
    tracker.start_session()
    for _ in range(4):
        tracker.record_chest()
    assert got.count("record") == 1


def test_sessions_history_and_today(db):
    sid = db.start_session(time.time() - 600)
    for _ in range(5):
        db.add_chest(sid)
    db.add_token(sid, 0.9)
    db.add_chest(sid)
    db.end_session(sid)
    rows = db.sessions()
    assert len(rows) == 1
    r = rows[0]
    assert (r.chests, r.tokens, r.since_token_at_end) == (6, 1, 1)
    assert r.duration >= 599
    st = db.stats()
    assert st.today_chests == 6 and st.best_session == 6 and st.tracked_seconds >= 599
    assert st.fewest_chests_for_token == 5


def test_short_empty_session_is_discarded(db):
    sid = db.start_session()
    db.end_session(sid)
    assert db.sessions() == []


def test_export_backup_restore_reset(db, tmp_path):
    sid = db.start_session()
    for _ in range(3):
        db.add_chest(sid)
    db.export_json(tmp_path / "e.json")
    data = json.loads((tmp_path / "e.json").read_text(encoding="utf-8"))
    assert len(data["chest_events"]) == 3
    db.export_csv(tmp_path / "e.csv")
    assert "coffres" in (tmp_path / "e.csv").read_text(encoding="utf-8-sig")
    db.backup(tmp_path / "b.db")
    db.reset()
    assert db.total_chests() == 0
    db.restore(tmp_path / "b.db")
    assert db.total_chests() == 3


def test_undo_last_chest(tracker):
    tracker.record_chest()
    tracker.record_chest()
    assert tracker.undo_last_chest()
    assert tracker.stats().total_chests == 1


def test_config_roundtrip(tmp_path):
    c = Config(tmp_path / "c.json")
    c.set("overlay", "opacity", 0.5)
    c2 = Config(tmp_path / "c.json")
    assert c2.get("overlay", "opacity") == 0.5
    assert c2.get("detection", "fps") == 15  # valeurs par défaut fusionnées
