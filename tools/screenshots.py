"""Génère des captures de l'interface avec des données de démonstration (docs/ et vérification visuelle).

Usage : QT_QPA_PLATFORM=offscreen python tools/screenshots.py docs/
"""
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("PIRATE_TRACKER_HOME", tempfile.mkdtemp(prefix="pt_shots_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pirate_tracker.database import Database  # noqa: E402
from pirate_tracker import levels  # noqa: E402


def seed_demo(db: Database):
    random.seed(4)
    now = time.time()
    total = 0
    for day in range(13, -1, -1):
        for _ in range(random.choice([0, 1, 1, 2])):
            start = now - day * 86400 - random.randint(3600, 30000)
            sid = db.start_session(start)
            n = random.randint(4, 22)
            for i in range(n):
                before = total
                db.add_chest(sid, 0.9, "prompt+burst", ts=start + 60 + i * 90)
                total += 1
                for kind, st in levels.transitions(before, total, [10, 25, 50, 100, 200]):
                    db.conn.execute("INSERT INTO level_events(ts, kind, level, stars, total_chests) VALUES (?,?,?,?,?)",
                                    (start + 60 + i * 90, kind, st.level, st.stars, total))
                if total in (41, 133):
                    db.add_token(sid, 0.93, ts=start + 70 + i * 90)
            db.conn.execute("UPDATE sessions SET ended_at=?, last_seen=? WHERE id=?",
                            (start + 60 + n * 90 + 300, start + 60 + n * 90 + 300, sid))
    db.conn.commit()


def main(out: str):
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from pirate_tracker.app import AppContext
    from pirate_tracker.ui import theme as T

    app.setStyle("Fusion")
    app.setFont(T.ui_font(10))
    app.setStyleSheet(T.STYLESHEET)
    seed_demo(Database())
    ctx = AppContext(app)
    ctx.engine.stop()
    ctx.tracker.start_session()
    for _ in range(3):
        ctx.db.add_chest(ctx.tracker.session_id)
    ctx.window.resize(1360, 940)
    ctx.window.show()
    for key in ctx.window.pages:
        ctx.window.show_page(key)
        for _ in range(30):
            app.processEvents()
            time.sleep(0.01)
        ctx.window.grab().save(str(out_dir / f"{key}.png"))
    ctx.refresh_all(animate=False)
    ctx.overlay.grab().save(str(out_dir / "widget.png"))
    ctx.celebration.play(92, 2)
    t0 = time.time()
    while time.time() - t0 < 1.2:
        app.processEvents()
        time.sleep(0.01)
    ctx.celebration.grab().save(str(out_dir / "token_celebration.png"))
    ctx.quit()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs")
