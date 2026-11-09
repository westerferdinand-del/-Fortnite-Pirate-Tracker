"""Pages Tableau de bord, Historique et Progression."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import levels
from . import icons
from . import theme as T
from .widgets import (BarChart, Card, GlowProgress, LineChart, StarBar, StatCard, StatusPill, fmt_duration, h1, h2,
                      muted)


def scroll_page(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    inner.setObjectName("page")
    sa.setWidget(inner)
    sa.viewport().setObjectName("page")  # style via la feuille globale (QWidget#page), sans cascade
    return sa


class HeroCard(QWidget):
    """Grand compteur de coffres illustré + niveau et étoiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(210)
        self.total = 0
        self.level = levels.compute_level(0, [10, 25, 50, 100, 200])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(230, 24, 28, 22)
        col = QVBoxLayout()
        col.setSpacing(4)
        cap = QLabel("COFFRES OUVERTS AU TOTAL")
        cap.setObjectName("muted")
        cap.setFont(T.ui_font(9, QFont.Bold))
        self.big = QLabel("000")
        self.big.setFont(T.display_font(46))
        self.big.setStyleSheet(f"color: {T.GOLD};")
        self.level_lbl = QLabel("NIVEAU 1")
        self.level_lbl.setFont(T.display_font(14))
        self.stars = StarBar()
        self.stars.setFixedHeight(54)
        self.progress = GlowProgress()
        self.next_lbl = muted("")
        col.addWidget(cap)
        col.addWidget(self.big)
        row = QHBoxLayout()
        row.addWidget(self.level_lbl)
        row.addStretch(1)
        col.addLayout(row)
        col.addWidget(self.stars)
        col.addWidget(self.progress)
        col.addWidget(self.next_lbl)
        lay.addLayout(col, 1)

    def set_values(self, total: int, st: levels.LevelState, animate=True):
        self.total = total
        self.big.setText(f"{total:03d}")
        self.level_lbl.setText(f"NIVEAU {st.level}")
        self.stars.set_stars(st.stars, animate)
        self.progress.set_value(st.star_progress)
        remaining = st.next_star_at - st.chests_in_level
        nxt = "le niveau suivant" if st.stars == 4 else f"l'étoile {st.stars + 1}"
        self.next_lbl.setText(f"Encore {remaining} coffre{'s' if remaining > 1 else ''} pour {nxt}")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#24125a"))
        g.setColorAt(0.55, QColor("#120c2e"))
        g.setColorAt(1, QColor("#0a1638"))
        p.setPen(QPen(T.c(T.GOLD, 90), 1.2))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)
        halo = QRadialGradient(r.x() + 115, r.center().y(), 130)
        halo.setColorAt(0, T.c(T.GOLD, 90))
        halo.setColorAt(1, T.c(T.GOLD, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(r.x() - 15, r.center().y() - 130, 260, 260))
        icons.draw_chest(p, QRectF(r.x() + 35, r.center().y() - 80, 160, 160), opened=True)
        icons.draw_token(p, QRectF(r.x() + 150, r.center().y() - 92, 52, 52))
        p.end()


class DashboardPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(18)

        top = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.addWidget(h1("TABLEAU DE BORD"))
        self.session_lbl = muted("", wrap=False)
        title_col.addWidget(self.session_lbl)
        top.addLayout(title_col, 1)
        self.status = StatusPill()
        top.addWidget(self.status, 0, Qt.AlignTop)
        lay.addLayout(top)

        self.hero = HeroCard()
        lay.addWidget(self.hero)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {
            "tokens": StatCard("token", "Jetons trouvés", T.GOLD),
            "since": StatCard("flame", "Coffres depuis le dernier jeton", "#fb923c"),
            "today": StatCard("calendar", "Coffres aujourd'hui", T.BLUE),
            "session": StatCard("chest", "Session en cours", T.VIOLET),
            "record": StatCard("trophy", "Record (meilleure session)", T.GOLD),
            "time": StatCard("clock", "Temps de jeu suivi", T.CYAN),
        }
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)

        self.line = LineChart("Progression : coffres cumulés (pièces = jetons trouvés)")
        lay.addWidget(self.line)
        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.daily = BarChart("Coffres par jour (14 derniers jours)", T.VIOLET)
        self.per_session = BarChart("Coffres par session (12 dernières)", T.BLUE)
        charts.addWidget(self.daily)
        charts.addWidget(self.per_session)
        lay.addLayout(charts)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(inner))

    def refresh(self, animate: bool = True):
        tr = self.ctx.tracker
        s = tr.stats()
        st = tr.level()
        self.hero.set_values(s.total_chests, st, animate)
        self.cards["tokens"].set(str(s.total_tokens),
                                 f"Meilleure chance : {s.fewest_chests_for_token} coffres" if s.fewest_chests_for_token else "")
        self.cards["since"].set(f"{s.since_last_token:03d}")
        self.cards["today"].set(str(s.today_chests), f"Meilleur jour : {s.best_day}")
        self.cards["session"].set(str(s.session_chests), fmt_duration(s.session_seconds) if tr.session_id else "aucune session")
        self.cards["record"].set(str(s.best_session), f"{s.sessions_count} session{'s' if s.sessions_count > 1 else ''}")
        self.cards["time"].set(fmt_duration(s.tracked_seconds))
        self.session_lbl.setText(
            f"Session n°{tr.session_id} en cours" if tr.session_id else "Aucune session — lancez Fortnite pour démarrer"
        )

        db = tr.db
        pts = db.cumulative_series()
        marks = [row["ts"] for row in db.tokens()]
        self.line.set_data(pts, marks)
        today = datetime.now().date()
        counts = dict(db.daily_counts(14))
        days = []
        for i in range(13, -1, -1):
            d = datetime.fromordinal(today.toordinal() - i).date()
            days.append((d.strftime("%d/%m"), counts.get(d.isoformat(), 0)))
        self.daily.set_data(days if any(v for _, v in days) else [])
        sess = list(reversed(db.sessions(12)))
        self.per_session.set_data([(f"#{r.id}", r.chests) for r in sess])

    def set_status(self, level, message):
        self.status.set_status(level, message)


class HistoryPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(h1("HISTORIQUE DES PARTIES"), 1)
        for text, fn in (("Exporter CSV", ctx.export_csv), ("Exporter JSON", ctx.export_json)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        lay.addWidget(muted("Chaque session est enregistrée automatiquement, du lancement à la fermeture de Fortnite."))

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Date", "Heure", "Durée", "Coffres", "Jetons", "Coffres depuis le dernier jeton"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setShowGrid(False)
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.addWidget(self.table)
        lay.addWidget(card, 3)

        lay.addWidget(h2("Jetons pirates trouvés"))
        self.tokens = QTableWidget(0, 4)
        self.tokens.setHorizontalHeaderLabels(["Date", "Coffres avant de le trouver", "Confiance", "Capture"])
        self.tokens.verticalHeader().setVisible(False)
        self.tokens.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tokens.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tokens.setShowGrid(False)
        self.tokens.cellDoubleClicked.connect(self._open_capture)
        card2 = Card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(8, 8, 8, 8)
        c2.addWidget(self.tokens)
        lay.addWidget(card2, 1)

    @staticmethod
    def _item(text, align=Qt.AlignCenter, color=None):
        it = QTableWidgetItem(str(text))
        it.setTextAlignment(align)
        if color:
            it.setForeground(QColor(color))
        return it

    def refresh(self, *_):
        rows = self.ctx.tracker.db.sessions()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = datetime.fromtimestamp(r.started_at)
            live = r.ended_at is None
            self.table.setItem(i, 0, self._item(d.strftime("%d/%m/%Y")))
            self.table.setItem(i, 1, self._item(d.strftime("%H:%M") + ("  • en cours" if live else ""),
                                                color=T.GREEN if live else None))
            self.table.setItem(i, 2, self._item(fmt_duration(r.duration)))
            self.table.setItem(i, 3, self._item(r.chests, color=T.GOLD))
            self.table.setItem(i, 4, self._item(r.tokens, color=T.GOLD if r.tokens else None))
            self.table.setItem(i, 5, self._item(r.since_token_at_end))
        toks = self.ctx.tracker.db.tokens()
        self.tokens.setRowCount(len(toks))
        for i, t in enumerate(toks):
            self.tokens.setItem(i, 0, self._item(datetime.fromtimestamp(t["ts"]).strftime("%d/%m/%Y %H:%M")))
            self.tokens.setItem(i, 1, self._item(t["chests_since_previous"], color=T.GOLD))
            self.tokens.setItem(i, 2, self._item(f"{t['confidence'] * 100:.0f} %"))
            it = self._item("Ouvrir (double-clic)" if t["screenshot"] else "—")
            it.setData(Qt.UserRole, t["screenshot"])
            self.tokens.setItem(i, 3, it)

    def _open_capture(self, row, col):
        it = self.tokens.item(row, 3)
        path = it.data(Qt.UserRole) if it else None
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


class ProgressPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(16)
        lay.addWidget(h1("ÉTOILES & NIVEAUX"))

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(26, 22, 26, 22)
        self.level_big = QLabel("NIVEAU 1")
        self.level_big.setFont(T.display_font(34))
        self.level_big.setStyleSheet(f"color: {T.GOLD};")
        self.level_big.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.level_big)
        self.stars = StarBar()
        self.stars.setMinimumHeight(96)
        cl.addWidget(self.stars)
        self.bar = GlowProgress()
        cl.addWidget(self.bar)
        self.detail = muted("")
        self.detail.setAlignment(Qt.AlignCenter)
        cl.addWidget(self.detail)
        lay.addWidget(card)

        th = Card()
        tl = QVBoxLayout(th)
        tl.setContentsMargins(22, 18, 22, 18)
        tl.addWidget(h2("Paliers personnalisables"))
        tl.addWidget(muted("Nombre de coffres (depuis le début du niveau) pour obtenir chaque étoile. "
                           "La 5e étoile fait passer au niveau suivant."))
        row = QHBoxLayout()
        self.spins = []
        for i in range(5):
            col = QVBoxLayout()
            lab = QLabel(f"★ {i + 1}")
            lab.setObjectName("gold")
            lab.setAlignment(Qt.AlignCenter)
            sp = QSpinBox()
            sp.setRange(1, 100000)
            col.addWidget(lab)
            col.addWidget(sp)
            row.addLayout(col)
            self.spins.append(sp)
        save = QPushButton("Enregistrer les paliers")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        row.addSpacing(10)
        row.addWidget(save, 0, Qt.AlignBottom)
        tl.addLayout(row)
        lay.addWidget(th)

        lay.addWidget(h2("Historique des niveaux"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date", "Évènement", "Niveau", "Coffres au total"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(260)
        hc = Card()
        hl = QVBoxLayout(hc)
        hl.setContentsMargins(8, 8, 8, 8)
        hl.addWidget(self.table)
        lay.addWidget(hc)
        lay.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(inner))

    def refresh(self, animate: bool = True):
        tr = self.ctx.tracker
        st = tr.level()
        self.level_big.setText(f"NIVEAU {st.level}")
        self.stars.set_stars(st.stars, animate)
        self.bar.set_value(st.level_progress)
        self.detail.setText(f"{st.chests_in_level} / {st.level_span} coffres dans ce niveau · "
                            f"prochaine étoile à {st.next_star_at}")
        for sp, v in zip(self.spins, tr.thresholds):
            sp.blockSignals(True)
            sp.setValue(int(v))
            sp.blockSignals(False)
        rows = tr.db.level_history()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [datetime.fromtimestamp(r["ts"]).strftime("%d/%m/%Y %H:%M"),
                    "Nouveau niveau !" if r["kind"] == "level" else f"Étoile {r['stars']} obtenue",
                    r["level"], r["total_chests"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignCenter)
                if j == 1 and r["kind"] == "level":
                    it.setForeground(QColor(T.GOLD))
                self.table.setItem(i, j, it)

    def _save(self):
        vals = [sp.value() for sp in self.spins]
        try:
            levels.validate_thresholds(vals)
        except ValueError as e:
            QMessageBox.warning(self, "Paliers invalides", str(e))
            return
        self.ctx.config.set("levels", "star_thresholds", vals)
        self.ctx.refresh_all(animate=False)
