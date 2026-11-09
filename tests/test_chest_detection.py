"""Tests de la détection des coffres sur des séquences synthétiques.

Chaque scénario contrôle un exigence : ouverture reconnue, pas de double comptage,
coffre fermé ignoré, éloignement sans ouverture ignoré, etc.
"""
import pytest

from pirate_tracker.detection import ChestDetector, ChestDetectorConfig
from pirate_tracker.detection.common import to_work
from tests.synthetic import Scene, prompt_template_from_scene, render


@pytest.fixture(scope="module")
def template():
    return prompt_template_from_scene("Coffre")


def run(scene, templates=None, mode="prompt+burst"):
    det = ChestDetector(ChestDetectorConfig(mode=mode), templates or [])
    events = []
    for t, img in render(scene):
        ev = det.process(img, t)
        if ev:
            events.append(ev)
    return events, det


def test_prompt_is_recognised(template):
    det = ChestDetector(ChestDetectorConfig(), [template])
    scores_on, scores_off = [], []
    for t, img in render(Scene(duration=2, prompts=[(1.0, 2.0, "Coffre")], seed=3)):
        (scores_on if t >= 1.0 else scores_off).append(det.prompt_score(to_work(img)))
    assert min(scores_on) > 0.8
    assert max(scores_off) < 0.5


def test_single_open_counts_once(template):
    scene = Scene(duration=6, prompts=[(1.0, 2.2, "Coffre")], opens=[2.2], seed=1)
    events, _ = run(scene, [template])
    assert len(events) == 1
    assert 2.1 <= events[0].t <= 3.5
    assert events[0].method == "prompt+burst"


def test_walk_away_without_opening_is_not_counted(template):
    # L'invite apparaît, le joueur tourne la caméra et s'en va : pas d'ouverture
    scene = Scene(duration=6, prompts=[(1.0, 2.0, "Coffre")], pans=[(2.0, 3.5, 900)], seed=2)
    events, _ = run(scene, [template])
    assert events == []


def test_closed_chest_glow_alone_is_not_counted(template):
    scene = Scene(duration=8, seed=4)
    assert run(scene, [template])[0] == []
    assert run(scene, mode="burst")[0] == []  # même sans calibrage


def test_explosion_without_prompt_is_ignored_in_prompt_mode(template):
    scene = Scene(duration=5, flashes=[1.5, 3.0], seed=5)
    events, _ = run(scene, [template])
    assert events == []


def test_two_chests_count_two(template):
    scene = Scene(duration=11, prompts=[(1.0, 2.2, "Coffre"), (6.0, 7.0, "Coffre")], opens=[2.2, 7.0], seed=6)
    events, _ = run(scene, [template])
    assert len(events) == 2


def test_prompt_flicker_then_open_counts_once(template):
    # L'invite disparaît une image (occlusion) puis revient, puis le coffre s'ouvre
    scene = Scene(duration=6, prompts=[(1.0, 1.6, "Coffre"), (1.67, 2.4, "Coffre")], opens=[2.4], seed=7)
    events, _ = run(scene, [template])
    assert len(events) == 1


def test_long_burst_and_loot_do_not_double_count(template):
    # Éclat d'ouverture suivi d'un second éclat (butin doré) 0,8 s plus tard
    scene = Scene(duration=6, prompts=[(1.0, 2.0, "Coffre")], opens=[2.0], flashes=[2.8], seed=8)
    events, _ = run(scene, [template])
    assert len(events) == 1


def test_other_container_prompt_not_counted(template):
    # Invite « Fouiller » d'une caisse de munitions : le libellé diffère → pas un coffre
    scene = Scene(duration=6, prompts=[(1.0, 2.2, "Caisse de munitions")], opens=[2.2], seed=9)
    events, det = run(scene, [template])
    assert events == []


def test_burst_only_fallback_detects_open():
    scene = Scene(duration=6, opens=[2.0], seed=10)
    events, det = run(scene, mode="burst")
    assert det.effective_mode == "burst"
    assert len(events) == 1


def test_missing_templates_falls_back_to_burst():
    det = ChestDetector(ChestDetectorConfig(mode="prompt+burst"), [])
    assert det.effective_mode == "burst"
