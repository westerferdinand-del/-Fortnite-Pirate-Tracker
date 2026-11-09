"""Tests de la détection du jeton pirate (vrai jeton vs images ressemblantes)."""
import cv2
import pytest

from pirate_tracker.detection import TokenDetector, TokenDetectorConfig
from pirate_tracker.detection.token import TOKEN_WORK_WIDTH
from tests.synthetic import W, Scene, render, token_image


@pytest.fixture(scope="module")
def template():
    # Modèle : icône découpée puis ramenée à l'échelle de travail (comme le calibrage)
    k = TOKEN_WORK_WIDTH / W
    img = token_image("real", 96)
    return cv2.resize(img, None, fx=k, fy=k)


def run(scene, template):
    det = TokenDetector(TokenDetectorConfig(), [template])
    events = []
    for i, (t, img) in enumerate(render(scene)):
        if i % 5:  # ~3 analyses / s comme dans l'application
            continue
        ev = det.process(img, t)
        if ev:
            events.append(ev)
    return events


@pytest.mark.parametrize("scale", [0.7, 1.0, 1.4])
def test_real_token_detected_once(template, scale):
    scene = Scene(duration=6, tokens=[(1.0, 5.0, "real", scale)], seed=11)
    events = run(scene, template)
    assert len(events) == 1
    assert 1.0 <= events[0].t <= 3.0


def test_recoloured_lookalike_rejected(template):
    scene = Scene(duration=5, tokens=[(1.0, 4.5, "recolor", 1.0)], seed=12)
    assert run(scene, template) == []


def test_ordinary_coin_rejected(template):
    scene = Scene(duration=5, tokens=[(1.0, 4.5, "coin", 1.0)], seed=13)
    assert run(scene, template) == []


def test_single_frame_glimpse_rejected(template):
    # Un jeton visible ~0,1 s (une seule analyse) ne suffit pas : persistance requise
    scene = Scene(duration=4, tokens=[(1.0, 1.1, "real", 1.0)], seed=14)
    assert run(scene, template) == []


def test_token_rearms_after_disappearing(template):
    scene = Scene(duration=12, tokens=[(1.0, 3.0, "real", 1.0), (7.5, 10.0, "real", 1.0)], seed=15)
    assert len(run(scene, template)) == 2


def test_no_template_never_detects():
    det = TokenDetector(TokenDetectorConfig(), [])
    for t, img in render(Scene(duration=1, tokens=[(0, 1, "real", 1.0)])):
        assert det.process(img, t) is None
