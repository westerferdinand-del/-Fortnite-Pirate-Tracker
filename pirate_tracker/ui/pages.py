"""Pages : Tableau de bord, Historique des parties, Récompenses, Étoiles & niveaux."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import items as items_mod
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


def make_table(headers: list[str], min_height: int = 0, stretch: int | None = None) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(False)
    t.horizontalHeader().setMinimumSectionSize(90)
    t.setShowGrid(False)
    if min_height:
        t.setMinimumHeight(min_height)
    t.horizontalHeader().setSectionResizeMode(len(headers) - 1 if stretch is None else stretch, QHeaderView.Stretch)
    return t


def cell(text, align=Qt.AlignCenter, color=None, bold=False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(align)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def carded(widget: QWidget) -> Card:
    c = Card()
    lay = QVBoxLayout(c)
    lay.setContentsMargins(8, 8, 8, 8)
    lay.addWidget(widget)
    return c


def playlist_name(p: str | None) -> str:
    if not p:
        return "—"
    s = p.replace("Playlist_", "")
    low = s.lower()
    team = "Solo" if "solo" in low else "Duo" if "duo" in low else "Trio" if "trio" in low else \
        "Escouade" if "squad" in low else ""
    mode = "Zéro construction" if "nobuild" in low else "Construction" if "default" in low or team else ""
    out = " · ".join(x for x in (mode, team) if x)
    return out or s


class HeroCard(QWidget):
    """Grand compteur de coffres illustré + niveau et étoiles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(210)
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
        col.addWidget(self.level_lbl)
        col.addWidget(self.stars)
        col.addWidget(self.progress)
        col.addWidget(self.next_lbl)
        lay.addLayout(col, 1)

    def set_values(self, total: int, st: levels.LevelState, animate=True):
        self.big.setText(f"{total:03d}")
        self.level_lbl.setText(f"NIVEAU {st.level}")
        self.stars.set_stars(st.stars, animate)
        self.progress.set_value(st.star_progress)
        remaining = st.next_star_at - st.chests_in_level
        nxt = "le niveau suivant" if st.stars == 4 else f"l'étoile {st.stars + 1}"
        self.next_lbl.setText(f"Encore {remaining} coffre{'s' if remaining > 1 else ''} pour {nxt}")

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
        self.sub_lbl = muted("", wrap=False)
        title_col.addWidget(self.sub_lbl)
        top.addLayout(title_col, 1)
        self.status = StatusPill()
        top.addWidget(self.status, 0, Qt.AlignTop)
        lay.addLayout(top)

        self.hero = HeroCard()
        lay.addWidget(self.hero)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {
            "last": StatCard("chest_open", "Coffres à la dernière partie", T.VIOLET),
            "avg": StatCard("chest", "Moyenne de coffres par partie", T.GOLD),
            "since": StatCard("flame", "Coffres depuis le dernier jeton", "#fb923c"),
            "today": StatCard("calendar", "Coffres aujourd'hui", T.BLUE),
            "record": StatCard("trophy", "Record (meilleure partie)", T.GOLD),
            "time": StatCard("clock", "Temps de jeu analysé", T.CYAN),
        }
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)

        self.line = LineChart("Progression : coffres ouverts au total")
        lay.addWidget(self.line)
        charts = QHBoxLayout()
        charts.setSpacing(14)
        self.daily = BarChart("Coffres par jour (14 derniers jours)", T.VIOLET)
        self.per_match = BarChart("Coffres par partie (15 dernières)", T.BLUE)
        charts.addWidget(self.daily)
        charts.addWidget(self.per_match)
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
        if s.last_match_chests is None:
            self.cards["last"].set("—", "aucune partie analysée")
        else:
            when = datetime.fromtimestamp(s.last_match_at).strftime("%d/%m %H:%M")
            place = f" · {s.last_match_placement}e" if s.last_match_placement else ""
            self.cards["last"].set(str(s.last_match_chests), f"{when}{place}")
        avg = s.total_chests / s.matches_count if s.matches_count else 0
        self.cards["avg"].set(f"{avg:.1f}".replace(".", ","), f"sur {s.matches_count} partie{'s' if s.matches_count > 1 else ''}")
        self.cards["since"].set(f"{s.since_last_token:03d}")
        self.cards["today"].set(str(s.today_chests), f"Meilleur jour : {s.best_day}")
        self.cards["record"].set(str(s.best_match), "coffres en une seule partie")
        self.cards["time"].set(fmt_duration(s.tracked_seconds))
        self.sub_lbl.setText("Mis à jour automatiquement à la fin de chaque partie, grâce aux replays de Fortnite")

        db = tr.db
        self.line.set_data(db.cumulative_series())
        today = datetime.now().date()
        counts = dict(db.daily_counts(14))
        days = []
        for i in range(13, -1, -1):
            d = datetime.fromordinal(today.toordinal() - i).date()
            days.append((d.strftime("%d/%m"), counts.get(d.isoformat(), 0)))
        self.daily.set_data(days if any(v for _, v in days) else [])
        ms = [m for m in tr.db.matches(15) if m.ok]
        self.per_match.set_data([(datetime.fromtimestamp(m.started_at).strftime("%d/%m"), m.chests)
                                 for m in reversed(ms)])

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
        lay.addWidget(muted("Chaque partie est ajoutée automatiquement quand Fortnite termine d'écrire son replay. "
                            "Sélectionnez une partie pour voir les objets obtenus."))

        self.table = make_table(["Date", "Durée", "Mode", "Classement", "Élim.", "Coffres", "Analyse"], stretch=2)
        self.table.itemSelectionChanged.connect(self._show_items)
        lay.addWidget(carded(self.table), 3)

        row = QHBoxLayout()
        self.detail_title = h2("Objets obtenus pendant la partie")
        row.addWidget(self.detail_title, 1)
        self.del_btn = QPushButton("Retirer cette partie du compteur")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self._delete)
        row.addWidget(self.del_btn)
        lay.addLayout(row)
        self.items = make_table(["Moment", "Objet", "Rareté", "Quantité"], stretch=1)
        lay.addWidget(carded(self.items), 2)
        self._rows = []

    def refresh(self, *_):
        self._rows = self.ctx.tracker.db.matches()
        self.table.setRowCount(len(self._rows))
        for i, m in enumerate(self._rows):
            d = datetime.fromtimestamp(m.started_at)
            self.table.setItem(i, 0, cell(d.strftime("%d/%m/%Y %H:%M")))
            self.table.setItem(i, 1, cell(fmt_duration(m.duration)))
            self.table.setItem(i, 2, cell(playlist_name(m.playlist)))
            place = f"{m.placement}e / {m.total_players}" if m.placement and m.total_players else (
                f"{m.placement}e" if m.placement else "—")
            self.table.setItem(i, 3, cell(place, color=T.GOLD if m.placement == 1 else None))
            self.table.setItem(i, 4, cell("—" if m.eliminations is None else m.eliminations))
            self.table.setItem(i, 5, cell(m.chests, color=T.GOLD, bold=True))
            if not m.ok:
                status = cell("Échec", color=T.RED)
                status.setToolTip(m.error or "")
            elif m.warnings:
                status = cell("OK (avertissement)", color=T.ORANGE)
                status.setToolTip("\n".join(m.warnings))
            else:
                status = cell("OK", color=T.GREEN)
            self.table.setItem(i, 6, status)
        self._show_items()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if rows and rows[0].row() < len(self._rows):
            return self._rows[rows[0].row()]
        return None

    def _show_items(self):
        m = self._selected()
        self.del_btn.setEnabled(m is not None)
        if m is None:
            self.items.setRowCount(0)
            self.detail_title.setText("Objets obtenus pendant la partie (sélectionnez une partie)")
            return
        rows = self.ctx.tracker.db.match_items(m.id)
        self.detail_title.setText(f"Objets obtenus pendant la partie du "
                                  f"{datetime.fromtimestamp(m.started_at):%d/%m/%Y %H:%M} ({len(rows)})")
        self.items.setRowCount(len(rows))
        for i, r in enumerate(rows):
            info = items_mod.describe(r["item"])
            t = r["ts"] - m.started_at
            self.items.setItem(i, 0, cell(f"{int(t // 60):02d}:{int(t % 60):02d}"))
            name = cell(info.name, Qt.AlignLeft | Qt.AlignVCenter, info.color)
            name.setToolTip(r["item"])
            self.items.setItem(i, 1, name)
            self.items.setItem(i, 2, cell(info.rarity or "—", color=info.color))
            self.items.setItem(i, 3, cell(r["count"] or 1))

    def _delete(self):
        m = self._selected()
        if m and QMessageBox.question(self, "Retirer la partie",
                                      "Retirer cette partie et ses coffres du compteur ?") == QMessageBox.Yes:
            self.ctx.tracker.delete_match(m.id)


class RewardsPage(QWidget):
    """Tout ce que le joueur a déjà obtenu (objets ramassés) + désignation du jeton pirate."""

    FILTERS = [("all", "Tout"), ("arme", "Armes"), ("soin", "Soins"), ("objet", "Objets"),
               ("matériaux", "Matériaux"), ("munitions", "Munitions")]

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(h1("RÉCOMPENSES OBTENUES"), 1)
        self.filter = QComboBox()
        for k, lbl in self.FILTERS:
            self.filter.addItem(lbl, k)
        self.filter.setCurrentIndex(1)
        self.filter.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.filter)
        lay.addLayout(top)

        self.summary = QHBoxLayout()
        self.cards = {
            "distinct": StatCard("list", "Objets différents obtenus", T.VIOLET),
            "legend": StatCard("star", "Objets légendaires / mythiques", T.GOLD),
        }
        for c in self.cards.values():
            self.summary.addWidget(c)
        lay.addLayout(self.summary)

        lay.addWidget(muted("Le jeton pirate est reconnu automatiquement d'après le nom de l'objet dans le replay. "
                            "Si son nom n'est pas reconnu, sélectionnez-le dans la liste puis cliquez sur "
                            "« C'est le jeton pirate » : toutes vos parties seront recalculées."))
        self.table = make_table(["Objet", "Rareté", "Obtenu", "Quantité totale", "Parties", "Première fois",
                                 "Jeton pirate"], stretch=0)
        lay.addWidget(carded(self.table), 1)
        row = QHBoxLayout()
        self.mark_btn = QPushButton("C'est le jeton pirate")
        self.mark_btn.setObjectName("gold")
        self.mark_btn.clicked.connect(lambda: self._mark(True))
        self.unmark_btn = QPushButton("Ce n'est pas le jeton")
        self.unmark_btn.clicked.connect(lambda: self._mark(False))
        row.addWidget(self.mark_btn)
        row.addWidget(self.unmark_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self._raw: list[str] = []

    def refresh(self, *_):
        tr = self.ctx.tracker
        is_token = tr.token_matcher()
        flt = self.filter.currentData()
        rows = tr.db.item_totals()
        shown = []
        legend = 0
        for r in rows:
            info = items_mod.describe(r["item"])
            if info.rarity in ("Légendaire", "Mythique"):
                legend += 1
            if flt != "all" and info.category != flt and not is_token(r["item"]):
                continue
            shown.append((r, info))
        shown.sort(key=lambda x: (not is_token(x[0]["item"]),
                                  ["Mythique", "Légendaire", "Épique", "Rare", "Peu commun", "Commun", ""].index(
                                      x[1].rarity) if x[1].rarity in ("Mythique", "Légendaire", "Épique", "Rare",
                                                                      "Peu commun", "Commun") else 6,
                                  -x[0]["times"]))
        self.cards["distinct"].set(str(len(rows)))
        self.cards["legend"].set(str(legend))
        self._raw = []
        self.table.setRowCount(len(shown))
        for i, (r, info) in enumerate(shown):
            tok = is_token(r["item"])
            name = cell(info.name, Qt.AlignLeft | Qt.AlignVCenter, T.GOLD if tok else info.color, bold=tok)
            name.setToolTip(r["item"])
            self.table.setItem(i, 0, name)
            self.table.setItem(i, 1, cell(info.rarity or "—", color=info.color))
            self.table.setItem(i, 2, cell(f"{r['times']} fois"))
            self.table.setItem(i, 3, cell(r["quantity"] or "—"))
            self.table.setItem(i, 4, cell(r["matches"]))
            self.table.setItem(i, 5, cell(datetime.fromtimestamp(r["first_ts"]).strftime("%d/%m/%Y")))
            self.table.setItem(i, 6, cell("OUI" if tok else "", color=T.GOLD, bold=True))
            self._raw.append(r["item"])

    def _mark(self, on: bool):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Jeton pirate", "Sélectionnez d'abord un objet dans la liste.")
            return
        raw = self._raw[rows[0].row()]
        self.ctx.tracker.mark_token_item(raw, on)


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
        self.table = make_table(["Date", "Évènement", "Niveau", "Coffres au total"], 260, stretch=1)
        lay.addWidget(carded(self.table))
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
            lvl = r["kind"] == "level"
            self.table.setItem(i, 0, cell(datetime.fromtimestamp(r["ts"]).strftime("%d/%m/%Y %H:%M")))
            self.table.setItem(i, 1, cell("Nouveau niveau !" if lvl else f"Étoile {r['stars']} obtenue",
                                          color=T.GOLD if lvl else None))
            self.table.setItem(i, 2, cell(r["level"]))
            self.table.setItem(i, 3, cell(r["total_chests"]))

    def _save(self):
        vals = [sp.value() for sp in self.spins]
        try:
            levels.validate_thresholds(vals)
        except ValueError as e:
            QMessageBox.warning(self, "Paliers invalides", str(e))
            return
        self.ctx.config.set("levels", "star_thresholds", vals)
        self.ctx.refresh_all(animate=False)
