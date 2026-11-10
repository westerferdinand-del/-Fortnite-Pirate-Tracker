"""Sons de notification : synthétisés au premier lancement (aucun fichier externe), personnalisables."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .paths import data_dir

RATE = 44100


def _write_wav(path: Path, samples: list[float]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))


def _tone(freqs: list[tuple[float, float, float]], decay: float = 6.0) -> list[float]:
    """freqs: (début s, fréquence Hz, durée s)."""
    total = max(t0 + d for t0, _, d in freqs) + 0.05
    out = [0.0] * int(total * RATE)
    for t0, f, d in freqs:
        start = int(t0 * RATE)
        for i in range(int(d * RATE)):
            t = i / RATE
            env = math.exp(-t * decay) * min(1.0, t * 200)
            v = env * (0.6 * math.sin(2 * math.pi * f * t) + 0.25 * math.sin(4 * math.pi * f * t)
                       + 0.1 * math.sin(6 * math.pi * f * t))
            if start + i < len(out):
                out[start + i] += 0.45 * v
    return out


BUILTIN = {
    # « ding » de pièce : deux notes aiguës
    "chest": lambda: _tone([(0, 1318.5, 0.25), (0.07, 1975.5, 0.45)], 7),
    # fanfare pirate : arpège majeur
    "token": lambda: _tone([(0, 523.3, 0.5), (0.12, 659.3, 0.5), (0.24, 784.0, 0.5), (0.36, 1046.5, 1.2),
                            (0.36, 1318.5, 1.2)], 2.5),
    # étoile / niveau
    "level": lambda: _tone([(0, 880.0, 0.3), (0.1, 1108.7, 0.3), (0.2, 1318.5, 0.7)], 4),
    "record": lambda: _tone([(0, 784.0, 0.25), (0.1, 987.8, 0.25), (0.2, 1174.7, 0.25), (0.3, 1568.0, 0.8)], 4),
}


ALIASES = {"match": "chest"}  # fin de partie analysée = son « pièce »


def builtin_path(name: str) -> Path:
    name = ALIASES.get(name, name)
    d = data_dir() / "sounds"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.wav"
    if not p.exists():
        _write_wav(p, BUILTIN[name]())
    return p


class SoundPlayer:
    """Lecture via QSoundEffect (Qt Multimedia)."""

    def __init__(self, config):
        self.config = config
        self._effects = {}

    def _effect(self, path: Path):
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect

        key = str(path)
        eff = self._effects.get(key)
        if eff is None:
            eff = QSoundEffect()
            eff.setSource(QUrl.fromLocalFile(key))
            self._effects[key] = eff
        return eff

    def play(self, name: str) -> None:
        s = self.config.section("sound")
        if not s.get("enabled", True):
            return
        custom = s.get(f"{name}_sound") or (s.get("level_sound") if name == "record" else "")
        path = Path(custom) if custom and Path(custom).exists() else builtin_path(name)
        try:
            eff = self._effect(path)
            eff.setVolume(float(s.get("volume", 0.7)))
            eff.play()
        except Exception:
            pass
