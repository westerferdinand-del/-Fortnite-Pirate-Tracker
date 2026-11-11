"""Génère pirate_tracker/assets/icon.ico et icon.png à partir de l'icône vectorielle."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QGuiApplication  # noqa: E402


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841
    from pirate_tracker.ui.icons import app_pixmap

    out = Path(__file__).resolve().parent.parent / "pirate_tracker" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    app_pixmap(256).save(str(out / "icon.png"))
    ok = app_pixmap(256).save(str(out / "icon.ico"))
    print("icon.ico", "ok" if ok else "ÉCHEC (plugin ICO absent)")
    web = Path(__file__).resolve().parent.parent / "pirate_tracker" / "companion" / "web"
    web.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QPainter, QPixmap

    from pirate_tracker.ui import icons, theme

    for size, name in ((512, "icon.png"), (180, "icon-180.png")):
        # Carré plein, sans transparence : iOS / Android arrondissent eux-mêmes les coins
        pm = QPixmap(size, size)
        pm.fill(QColor("#141417"))
        p = QPainter(pm)
        m = size * 0.22
        icons.draw(p, "chest", QRectF(m, m, size - 2 * m, size - 2 * m), theme.ACCENT, 1.8)
        p.end()
        pm.save(str(web / name))
    print("icônes de l'application mobile : ok")


if __name__ == "__main__":
    main()
