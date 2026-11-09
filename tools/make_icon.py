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


if __name__ == "__main__":
    main()
