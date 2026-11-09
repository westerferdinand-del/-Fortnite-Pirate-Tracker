"""Palette et feuille de style : noir profond, violet, bleu, or."""
from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#07060d"
BG2 = "#0e0b1a"
PANEL = "#141026"
PANEL2 = "#1b1533"
BORDER = "#2a2150"
TEXT = "#ece9ff"
MUTED = "#9a93c4"
VIOLET = "#8b5cf6"
VIOLET_D = "#5b21b6"
BLUE = "#3b82f6"
CYAN = "#22d3ee"
GOLD = "#fbbf24"
GOLD_D = "#b7791f"
GREEN = "#22c55e"
ORANGE = "#f59e0b"
RED = "#ef4444"


def c(hex_: str, alpha: int = 255) -> QColor:
    q = QColor(hex_)
    q.setAlpha(alpha)
    return q


def ui_font(size: int = 10, weight: int = QFont.Normal) -> QFont:
    families = set(QFontDatabase.families())
    for fam in ("Segoe UI Variable Display", "Segoe UI", "Inter", "Noto Sans", "DejaVu Sans"):
        if fam in families:
            f = QFont(fam, size)
            break
    else:
        f = QFont()
        f.setPointSize(size)
    f.setWeight(weight)
    return f


def display_font(size: int = 20) -> QFont:
    families = set(QFontDatabase.families())
    for fam in ("Bahnschrift", "Segoe UI Black", "Impact", "Noto Sans", "DejaVu Sans"):
        if fam in families:
            f = QFont(fam, size)
            break
    else:
        f = QFont()
        f.setPointSize(size)
    f.setWeight(QFont.Black)
    return f


STYLESHEET = f"""
* {{ color: {TEXT}; outline: none; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#page {{ background: transparent; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {VIOLET}; padding: 6px; border-radius: 6px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 800; letter-spacing: 1px; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; color: {TEXT}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#gold {{ color: {GOLD}; font-weight: 700; }}
QFrame#card {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {PANEL2}, stop:1 {PANEL});
    border: 1px solid {BORDER}; border-radius: 14px;
}}
QFrame#sidebar {{ background: {BG2}; border-right: 1px solid {BORDER}; }}
QPushButton {{
    background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 9px; padding: 8px 14px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {VIOLET}; background: #231b42; }}
QPushButton:pressed {{ background: {VIOLET_D}; }}
QPushButton:disabled {{ color: #5d5880; border-color: #1e1838; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {VIOLET_D}, stop:1 {BLUE}); border: none; color: white;
}}
QPushButton#primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {VIOLET}, stop:1 #60a5fa); }}
QPushButton#gold {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {GOLD_D}, stop:1 {GOLD}); border: none; color: #1a1205;
}}
QPushButton#danger {{ border-color: #5b1d2a; color: #fca5a5; }}
QPushButton#danger:hover {{ background: #3b1020; border-color: {RED}; }}
QPushButton#nav {{
    background: transparent; border: none; border-radius: 10px; text-align: left; padding: 11px 14px;
    color: {MUTED}; font-size: 14px; font-weight: 600;
}}
QPushButton#nav:hover {{ background: #18122e; color: {TEXT}; }}
QPushButton#nav:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2a1a5e, stop:1 transparent); color: white;
    border-left: 3px solid {GOLD};
}}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {BG2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 10px; min-height: 20px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:focus {{ border-color: {VIOLET}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {VIOLET}; selection-background-color: {VIOLET_D}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 38px; height: 20px; border-radius: 10px; background: #2a2448; border: 1px solid {BORDER}; }}
QCheckBox::indicator:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {VIOLET}, stop:1 {BLUE}); }}
QSlider::groove:horizontal {{ height: 6px; background: #2a2448; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {VIOLET}, stop:1 {GOLD}); border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; border-radius: 8px; background: {GOLD}; }}
QTableWidget {{
    background: transparent; border: none; gridline-color: {BORDER}; alternate-background-color: #110d20;
    selection-background-color: #2a1a5e;
}}
QHeaderView::section {{ background: {PANEL2}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 8px; font-weight: 700; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2e2557; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollArea {{ background: transparent; border: none; }}
QProgressBar {{ background: #1c1636; border: none; border-radius: 6px; height: 12px; text-align: center; font-size: 10px; }}
QProgressBar::chunk {{ border-radius: 6px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {VIOLET}, stop:1 {GOLD}); }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 12px; margin-top: 18px; padding: 14px; background: {PANEL}; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {GOLD}; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {VIOLET_D}; }}
"""
