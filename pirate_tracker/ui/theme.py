"""Direction artistique v2 : sobre, noir profond, une seule couleur d'accent, typographie Inter.

Règles :
- surfaces plates, bordures fines, aucun dégradé ni lueur ;
- l'accent (or doux) ne sert qu'aux chiffres clés et à l'élément actif ;
- hiérarchie par la taille et la graisse du texte, pas par la couleur.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

from ..paths import resource_path

# ---------------------------------------------------------------- couleurs
BG = "#0b0b0d"
SURFACE = "#121215"
SURFACE2 = "#18181c"
HOVER = "#1d1d22"
BORDER = "#232329"
BORDER2 = "#2e2e36"
TEXT = "#ededf0"
TEXT2 = "#a5a5ae"
MUTED = "#6c6c77"
ACCENT = "#e6b450"  # or doux
ACCENT_DIM = "#3a2f19"
GREEN = "#46c37b"
ORANGE = "#e0a23b"
RED = "#ef5b5b"

# Compatibilité avec l'ancien code (noms de la v1)
BG2, PANEL, PANEL2, GOLD, GOLD_D, VIOLET, VIOLET_D, BLUE, CYAN = (
    SURFACE, SURFACE, SURFACE2, ACCENT, ACCENT, ACCENT, ACCENT_DIM, TEXT2, TEXT2)

RARITY = {
    "Commun": "#9a9aa3", "Peu commun": "#4fbf6f", "Rare": "#4d9de0", "Épique": "#a77be0",
    "Légendaire": "#e0a23b", "Mythique": "#e6c34d",
}


def c(hex_: str, alpha: int = 255) -> QColor:
    q = QColor(hex_)
    q.setAlpha(alpha)
    return q


# ---------------------------------------------------------------- typographie
_FAMILY: str | None = None
_DISPLAY: str | None = None


def load_fonts() -> None:
    """Charge Inter (intégrée à l'application) ; repli sur Segoe UI si indisponible."""
    global _FAMILY, _DISPLAY
    if _FAMILY is not None:
        return
    fams, disp = set(), set()
    d = resource_path("assets", "fonts")
    for f in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf"):
        fid = QFontDatabase.addApplicationFont(str(d / f))
        if fid >= 0:
            fams.update(QFontDatabase.applicationFontFamilies(fid))
    fid = QFontDatabase.addApplicationFont(str(d / "InterDisplay-SemiBold.ttf"))
    if fid >= 0:
        disp.update(QFontDatabase.applicationFontFamilies(fid))
    available = set(QFontDatabase.families())
    fallback = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Noto Sans", "DejaVu Sans") if f in available),
                    "")
    _FAMILY = "Inter" if "Inter" in fams else (sorted(fams)[0] if fams else fallback)
    _DISPLAY = "Inter Display" if "Inter Display" in disp else _FAMILY


def font(px: float = 13, weight: int = QFont.Normal, display: bool = False, tabular: bool = False) -> QFont:
    load_fonts()
    f = QFont(_DISPLAY if display else _FAMILY)
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(QFont.Weight(weight))
    f.setHintingPreference(QFont.PreferNoHinting)
    if tabular:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)  # chiffres à chasse fixe (Qt ≥ 6.7)
        except (AttributeError, TypeError):
            pass
    if display:
        f.setLetterSpacing(QFont.PercentageSpacing, 98)
    return f


# Anciens noms (v1) conservés pour les modules non encore migrés
def ui_font(size: int = 10, weight: int = QFont.Normal) -> QFont:
    return font(size * 1.33, weight)


def display_font(size: int = 20) -> QFont:
    return font(size * 1.33, QFont.DemiBold, display=True, tabular=True)


STYLESHEET = f"""
* {{ color: {TEXT}; outline: none; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#page {{ background: {BG}; }}
QWidget#content {{ background: {BG}; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER2}; padding: 6px 8px; border-radius: 6px; }}

QLabel#title {{ font-size: 22px; font-weight: 600; }}
QLabel#subtitle {{ color: {MUTED}; font-size: 13px; }}
QLabel#section {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {TEXT2}; }}
QLabel#faint {{ color: {MUTED}; }}
QLabel#caps {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}

QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#sidebar {{ background: {BG}; border-right: 1px solid {BORDER}; }}
QFrame#hline {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}
QFrame#vline {{ background: {BORDER}; max-width: 1px; min-width: 1px; border: none; }}

QPushButton {{
    background: {SURFACE2}; border: 1px solid {BORDER2}; border-radius: 8px; padding: 7px 14px;
    font-weight: 500; color: {TEXT};
}}
QPushButton:hover {{ background: {HOVER}; border-color: #3a3a44; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER}; }}
QPushButton#primary {{ background: {TEXT}; color: {BG}; border: 1px solid {TEXT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#primary:disabled {{ background: {BORDER2}; color: {MUTED}; border-color: {BORDER2}; }}
QPushButton#ghost {{ background: transparent; border: 1px solid transparent; color: {TEXT2}; }}
QPushButton#ghost:hover {{ background: {SURFACE2}; color: {TEXT}; }}
QPushButton#danger {{ background: transparent; border: 1px solid #4a2626; color: {RED}; }}
QPushButton#danger:hover {{ background: #241414; }}
QPushButton#nav {{
    background: transparent; border: none; border-radius: 8px; text-align: left; padding: 8px 10px;
    color: {TEXT2}; font-weight: 500;
}}
QPushButton#nav:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#nav:checked {{ background: {SURFACE2}; color: {TEXT}; }}
QPushButton#chip {{
    background: transparent; border: 1px solid {BORDER2}; border-radius: 13px; padding: 0 14px;
    min-height: 26px; max-height: 26px; color: {TEXT2}; font-weight: 500;
}}
QPushButton#chip:hover {{ color: {TEXT}; }}
QPushButton#chip:checked {{ background: {TEXT}; color: {BG}; border-color: {TEXT}; }}

QComboBox, QSpinBox, QLineEdit {{
    background: {SURFACE2}; border: 1px solid {BORDER2}; border-radius: 8px; padding: 6px 10px; min-height: 20px;
}}
QComboBox:hover, QSpinBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color: #44444f; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE2}; border: 1px solid {BORDER2}; selection-background-color: {HOVER};
    padding: 4px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 0; }}
QCheckBox::indicator {{ width: 34px; height: 20px; border-radius: 10px; background: {BORDER2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; }}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER2}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {TEXT2}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {TEXT}; }}

QTableWidget {{
    background: transparent; border: none; gridline-color: transparent; selection-background-color: {SURFACE2};
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 0 10px; border-bottom: 1px solid {BORDER}; }}
QHeaderView {{ background-color: {SURFACE}; border: none; }}
QHeaderView::section {{
    background-color: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 10px; font-size: 11px; font-weight: 600;
}}
QTableCornerButton::section {{ background-color: {SURFACE}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3c3c46; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QProgressBar {{ background: {BORDER2}; border: none; border-radius: 2px; max-height: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {TEXT}; border-radius: 2px; }}
QMenu {{ background: {SURFACE2}; border: 1px solid {BORDER2}; padding: 4px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 16px; border-radius: 6px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QListWidget {{ background: transparent; border: none; }}
"""
