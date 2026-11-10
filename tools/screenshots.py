"""Génère des captures de l'interface avec des données de démonstration (docs/ et vérification visuelle).

Usage : QT_QPA_PLATFORM=offscreen python tools/screenshots.py docs/
"""
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("PIRATE_TRACKER_HOME", tempfile.mkdtemp(prefix="pt_shots_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

LOOT = ["WID_Assault_CoreAR_Athena_UC", "WID_Shotgun_CoreDPS_Athena_R", "WID_Pistol_Standard_Athena_C",
        "WID_SMG_Burst_Athena_VR", "WID_Sniper_Heavy_Athena_SR", "WID_Paprika_ShieldSmall", "Athena_Medkit",
        "Athena_WadsItemData", "AthenaAmmoDataBulletsMedium", "AthenaAmmoDataShells", "Athena_ShockGrenade",
        "WID_Hook_Gun_VR_Ore_T03"]


def demo_results():
    random.seed(4)
    now = datetime.now(timezone.utc)
    out = []
    n = 0
    for day in range(13, -1, -1):
        for k in range(random.choice([0, 1, 2, 3])):
            n += 1
            start = now - timedelta(days=day, hours=random.randint(1, 8), minutes=k * 25)
            chests = random.randint(1, 11)
            items = [{"t": 60 + i * 40, "item": random.choice(LOOT), "count": random.randint(1, 30)}
                     for i in range(random.randint(4, 14))]
            if n in (9, 27):
                items.append({"t": 700, "item": "Athena_PirateToken", "count": 1})
            out.append({"ok": True, "file": f"C:/Demos/UnsavedReplay-{n:03d}.replay",
                        "started_utc": start.strftime("%Y-%m-%dT%H:%M:%S"), "duration_s": random.randint(400, 1500),
                        "placement": random.randint(1, 60), "total_players": 100,
                        "eliminations": random.randint(0, 9),
                        "playlist": random.choice(["Playlist_DefaultSolo", "Playlist_NoBuildBR_Duo",
                                                   "Playlist_DefaultSquad"]),
                        "chests": [{"t": 50 + i * 60, "id": i, "kind": "Tiered_Chest_Athena",
                                    "how": "cassé" if random.random() < 0.25 else "ouvert",
                                    "special": random.random() < 0.08} for i in range(chests)],
                        "items": items})
    return out


def pump(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.01)


def main(out: str):
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from pirate_tracker.app import AppContext
    from pirate_tracker.ui import theme as T

    app.setStyle("Fusion")
    app.setFont(T.ui_font(10))
    app.setStyleSheet(T.STYLESHEET)
    ctx = AppContext(app, start_watcher=False)
    ctx.tracker.import_results(demo_results())
    ctx.window.resize(1360, 940)
    ctx.window.show()
    for key in ctx.window.pages:
        ctx.window.show_page(key)
        if key == "history":
            ctx.window.pages["history"].table.selectRow(0)
        pump(app, 0.4)
        ctx.window.grab().save(str(out_dir / f"{key}.png"))
    ctx.refresh_all(animate=False)
    pump(app, 0.2)
    ctx.overlay.grab().save(str(out_dir / "widget.png"))
    ctx.toast_w.notify("chest_open", "+7 coffres cette partie", "Total : 112 coffres", 5)
    pump(app, 0.5)
    ctx.toast_w.grab().save(str(out_dir / "toast.png"))
    ctx.quit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs")
