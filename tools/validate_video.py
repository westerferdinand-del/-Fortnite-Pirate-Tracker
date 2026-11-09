"""Valide la détection sur un enregistrement réel de partie Fortnite.

Usage :
    python tools/validate_video.py partie.mp4
    python tools/validate_video.py partie.mp4 --truth verite.txt

Le fichier ``--truth`` liste, une par ligne, les instants réels d'ouverture de coffre
(en secondes ou en mm:ss), notés en regardant la vidéo. L'outil calcule alors :
- vrais positifs (détection à moins de ``--tolerance`` s d'une vraie ouverture),
- faux positifs (détection sans ouverture réelle),
- coffres manqués,
- précision et rappel.

Les modèles (invite « Fouiller », jeton) et réglages utilisés sont ceux de
l'application (dossier de données), ou ceux de ``--templates``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pirate_tracker.config import Config  # noqa: E402
from pirate_tracker.detection.templates import TemplateStore  # noqa: E402
from pirate_tracker.engine import analyze_video  # noqa: E402
from pirate_tracker.paths import templates_dir  # noqa: E402


def parse_time(s: str) -> float:
    s = s.strip()
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        t = 0.0
        for x in parts:
            t = t * 60 + x
        return t
    return float(s)


def score(detected: list[float], truth: list[float], tolerance: float) -> dict:
    truth_left = sorted(truth)
    tp, fp = [], []
    for d in sorted(detected):
        match = next((t for t in truth_left if abs(t - d) <= tolerance), None)
        if match is None:
            fp.append(d)
        else:
            tp.append((match, d))
            truth_left.remove(match)
    precision = len(tp) / len(detected) if detected else (1.0 if not truth else 0.0)
    recall = len(tp) / len(truth) if truth else 1.0
    return {"true_positives": len(tp), "false_positives": fp, "missed": truth_left,
            "precision": round(precision, 3), "recall": round(recall, 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--truth", help="fichier des instants réels d'ouverture")
    ap.add_argument("--tolerance", type=float, default=2.0)
    ap.add_argument("--templates", help="dossier de modèles (défaut : celui de l'application)")
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    settings = Config().section("detection")
    store = TemplateStore(Path(args.templates) if args.templates else templates_dir())
    res = analyze_video(args.video, settings, store, fps=args.fps,
                        progress=lambda v: print(f"\r{v * 100:5.1f} %", end="", file=sys.stderr))
    print(file=sys.stderr)
    out = {"mode": res["mode"], "frames": res["frames"], "chests": res["chests"], "tokens": res["tokens"]}
    if args.truth:
        truth = [parse_time(line) for line in Path(args.truth).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.strip().startswith("#")]
        out["score"] = score([c["t"] for c in res["chests"]], truth, args.tolerance)

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    print(f"Mode : {res['mode']} · {res['frames']} images analysées")
    print(f"Coffres détectés : {len(res['chests'])}")
    for c in res["chests"]:
        print(f"  {int(c['t'] // 60):02d}:{c['t'] % 60:05.2f}  confiance {c['confidence']:.2f}  ({c['method']})")
    print(f"Jetons détectés : {len(res['tokens'])}")
    if "score" in out:
        s = out["score"]
        print(f"\nPrécision : {s['precision'] * 100:.1f} %   Rappel : {s['recall'] * 100:.1f} %")
        print(f"Faux positifs : {s['false_positives']}")
        print(f"Coffres manqués : {s['missed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
