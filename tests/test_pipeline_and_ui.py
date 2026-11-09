"""Tests de bout en bout : vidéo → moteur → compteur, et interface (sans écran)."""
import os
import sys

import cv2
import pytest

from pirate_tracker.detection.templates import TemplateStore
from pirate_tracker.detection.token import TOKEN_WORK_WIDTH
from pirate_tracker.engine import analyze_video
from tests.synthetic import W, Scene, prompt_template_from_scene, token_image, write_video


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    d = tmp_path_factory.mktemp("vid")
    scene = Scene(duration=16,
                  prompts=[(1, 2.2, "Coffre"), (5, 6, "Coffre"), (8, 9, "Caisse de munitions"), (11, 12, "Coffre")],
                  opens=[2.2, 6.0, 9.0, 12.0], flashes=[14], tokens=[(13, 15.5, "real", 1.0)], seed=21)
    return write_video(scene, str(d / "partie.mp4"))


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    s = TemplateStore(tmp_path_factory.mktemp("tpl"))
    s.add("prompt", prompt_template_from_scene())
    k = TOKEN_WORK_WIDTH / W
    s.add("token", cv2.resize(token_image("real", 96), None, fx=k, fy=k))
    return s


def test_analyze_video_pipeline(video, store):
    from pirate_tracker.config import DEFAULTS

    res = analyze_video(video, DEFAULTS["detection"], store)
    times = [c["t"] for c in res["chests"]]
    assert res["mode"] == "prompt+burst"
    assert len(times) == 3, times  # la caisse de munitions (t=9) et l'explosion (t=14) sont ignorées
    assert all(any(abs(t - o) < 1.5 for o in (2.2, 6.0, 12.0)) for t in times)
    assert len(res["tokens"]) == 1


def test_validate_tool_scoring():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from validate_video import parse_time, score

    assert parse_time("01:02.5") == 62.5
    s = score([2.3, 6.1, 20.0], [2.2, 6.0, 12.0], 1.0)
    assert s["true_positives"] == 2 and s["false_positives"] == [20.0] and s["missed"] == [12.0]


def test_ui_smoke(tmp_path, monkeypatch):
    """Construit toute l'application (fenêtre, widget, pages) et vérifie la mise à jour en direct."""
    monkeypatch.setenv("PIRATE_TRACKER_HOME", str(tmp_path))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from pirate_tracker.app import AppContext

    ctx = AppContext(app)
    try:
        ctx.engine.stop()
        for _ in range(11):
            ctx.tracker.record_chest(0.9, "prompt+burst")
        app.processEvents()
        assert ctx.overlay.values["chests"] == 11
        assert ctx.overlay.values["stars"] == 1
        ctx.tracker.record_token(0.95)
        app.processEvents()
        assert ctx.overlay.values["tokens"] == 1 and ctx.overlay.values["since"] == 0
        for key in ctx.window.pages:
            ctx.window.show_page(key)
            app.processEvents()
        dash = ctx.window.pages["dashboard"]
        assert dash.hero.big.text() == "011"
        assert ctx.window.pages["history"].table.rowCount() == 1
    finally:
        ctx.quit()
