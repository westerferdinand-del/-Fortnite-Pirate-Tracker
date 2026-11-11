"""Chances du jeton pirate (taux publié : 1 sur 137 500 par coffre)."""
import math

from pirate_tracker.odds import format_percent, token_odds


def test_probabilities():
    assert token_odds(0).probability_any == 0
    o = token_odds(137_500)
    assert math.isclose(o.probability_any, 1 - math.exp(-1), rel_tol=1e-4)  # ≈ 63,2 %
    assert math.isclose(o.expected_tokens, 1.0)
    assert o.openings_for_half == 95_308
    assert math.isclose(token_odds(o.openings_for_half).probability_any, 0.5, abs_tol=1e-5)
    assert format_percent(token_odds(2618).percent) == "1,9 %"
    assert format_percent(token_odds(20).percent) == "0,015 %"
    assert format_percent(token_odds(1).percent) == "0,00073 %"
    assert token_odds(10, one_in=1).probability_any == 1.0


def test_tracker_odds_include_chests_from_before(tmp_path):
    from pirate_tracker.config import Config
    from pirate_tracker.database import Database
    from pirate_tracker.tracker import Tracker

    db = Database(tmp_path / "o.db")
    tr = Tracker(db, Config(tmp_path / "s.json"))
    tr.set_initial_chests(2500)
    assert tr.odds().openings == 2500
    tr.config.set("token", "one_in", 1000)
    assert tr.odds().one_in == 1000
    db.close()
