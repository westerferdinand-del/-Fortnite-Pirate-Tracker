"""Pages v2 : Vue d'ensemble, Parties, Butin."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import items as items_mod
from . import theme as T
from ..odds import format_percent
from .widgets import (BarChart, Card, LiveChip, MatchTimeline, Metric, MetricStrip, StepProgress, animate_number, caps,
                      faint, fmt_date, fmt_duration, fmt_int,
                      hline, section, title)

CONTENT_MAX = 1120


# ---------------------------------------------------------------- outils
def page_shell(header: QWidget, body: QWidget, scroll: bool = True) -> QWidget:
    """En-tête + contenu centré à largeur maximale, défilant si besoin."""
    inner = QWidget()
    inner.setObjectName("content")
    outer = QHBoxLayout(inner)
    outer.setContentsMargins(40, 32, 40, 40)
    col = QWidget()
    col.setMaximumWidth(CONTENT_MAX)
    cl = QVBoxLayout(col)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(24)
    cl.addWidget(header)
    cl.addWidget(body, 1)
    outer.addWidget(col, 1)
    if not scroll:
        return inner
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setWidget(inner)
    sa.viewport().setObjectName("page")
    return sa


def header(title_text: str, subtitle: str = "", right: QWidget | None = None) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    col = QVBoxLayout()
    col.setSpacing(4)
    col.addWidget(title(title_text))
    if subtitle:
        s = faint(subtitle, wrap=False)
        s.setFont(T.font(13))
        col.addWidget(s)
    lay.addLayout(col, 1)
    if right is not None:
        lay.addWidget(right, 0, Qt.AlignBottom)
    return w


def make_table(headers: list[str], stretch: int = 0, min_height: int = 0) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(42)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setShowGrid(False)
    t.setFocusPolicy(Qt.NoFocus)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    h.setSectionResizeMode(stretch, QHeaderView.Stretch)
    h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    h.setHighlightSections(False)
    h.setMinimumSectionSize(70)
    t.setFont(T.font(13))
    if min_height:
        t.setMinimumHeight(min_height)
    return t


def cell(text, align=Qt.AlignLeft | Qt.AlignVCenter, color: str | None = None, weight: int | None = None,
         tabular: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(align)
    if color:
        it.setForeground(QColor(color))
    if weight or tabular:
        it.setFont(T.font(13, weight or QFont.Normal, tabular=tabular))
    return it


NUM = Qt.AlignRight | Qt.AlignVCenter


def playlist_name(p: str | None) -> str:
    if not p:
        return "—"
    low = p.lower()
    team = ("Solo" if "solo" in low else "Duo" if "duo" in low else "Trio" if "trio" in low else
            "Escouade" if "squad" in low else "")
    mode = "Zéro construction" if "nobuild" in low else ("Battle Royale" if team else "")
    out = " · ".join(x for x in (mode, team) if x)
    return out or p.replace("Playlist_", "").replace("_", " ")


def placement_text(m) -> str:
    if not m.placement:
        return "—"
    return f"#{m.placement}" + (f" / {m.total_players}" if m.total_players else "")


# ---------------------------------------------------------------- vue d'ensemble
class OverviewPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        # --- total
        hero = Card(padding=28)
        row = QHBoxLayout()
        row.setSpacing(40)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(caps("Coffres ouverts"))
        self.total = QLabel("0")
        self.total.setFont(T.font(64, QFont.DemiBold, display=True, tabular=True))
        left.addWidget(self.total)
        self.total_detail = faint("", wrap=False)
        self.total_detail.setFont(T.font(13))
        left.addWidget(self.total_detail)
        row.addLayout(left, 3)
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addStretch(1)
        lv = QHBoxLayout()
        self.level = QLabel("Niveau 1")
        self.level.setFont(T.font(15, QFont.DemiBold))
        self.step_lbl = faint("", wrap=False)
        lv.addWidget(self.level)
        lv.addStretch(1)
        lv.addWidget(self.step_lbl)
        right.addLayout(lv)
        self.steps = StepProgress()
        right.addWidget(self.steps)
        self.next_lbl = faint("", wrap=False)
        self.next_lbl.setFont(T.font(12))
        right.addWidget(self.next_lbl)
        right.addStretch(1)
        row.addLayout(right, 2)
        hero.lay.addLayout(row)
        lay.addWidget(hero)

        # --- chances du jeton pirate
        odds = Card(padding=24)
        orow = QHBoxLayout()
        orow.setSpacing(36)
        ol = QVBoxLayout()
        ol.setSpacing(6)
        ol.addWidget(caps("Jeton pirate"))
        self.odds_pct = QLabel("—")
        self.odds_pct.setFont(T.font(40, QFont.DemiBold, display=True, tabular=True))
        self.odds_pct.setStyleSheet(f"color: {T.ACCENT};")
        ol.addWidget(self.odds_pct)
        self.odds_sub = faint("", wrap=False)
        self.odds_sub.setFont(T.font(13))
        ol.addWidget(self.odds_sub)
        orow.addLayout(ol, 3)
        orr = QVBoxLayout()
        orr.setSpacing(10)
        orr.addStretch(1)
        oh = QHBoxLayout()
        self.odds_goal = QLabel("")
        self.odds_goal.setFont(T.font(13, QFont.Medium))
        oh.addWidget(self.odds_goal)
        oh.addStretch(1)
        self.odds_goal_pct = faint("", wrap=False)
        oh.addWidget(self.odds_goal_pct)
        orr.addLayout(oh)
        self.odds_bar = StepProgress()
        self.odds_bar.steps = 1
        orr.addWidget(self.odds_bar)
        self.odds_note = faint("", wrap=True)
        self.odds_note.setFont(T.font(12))
        orr.addWidget(self.odds_note)
        orr.addStretch(1)
        orow.addLayout(orr, 2)
        odds.lay.addLayout(orow)
        lay.addWidget(odds)

        # --- chiffres clés
        self.strip = MetricStrip(["Dernière partie", "Aujourd'hui", "Moyenne par partie", "Depuis le dernier jeton"])
        lay.addWidget(self.strip)

        # --- graphique + records
        mid = QHBoxLayout()
        mid.setSpacing(16)
        chart_card = Card()
        hc = QHBoxLayout()
        hc.addWidget(section("Coffres par jour"))
        hc.addStretch(1)
        hc.addWidget(faint("30 derniers jours", wrap=False))
        chart_card.lay.addLayout(hc)
        self.chart = BarChart(height=200)
        chart_card.lay.addWidget(self.chart)
        mid.addWidget(chart_card, 2)
        rec = Card()
        rec.lay.addWidget(section("Records"))
        self.records = {}
        grid = QGridLayout()
        grid.setVerticalSpacing(18)
        grid.setHorizontalSpacing(16)
        for i, key in enumerate(("Meilleure partie", "Meilleur jour", "Parties analysées", "Temps de jeu")):
            m = Metric(key, big=20)
            grid.addWidget(m, i // 2, i % 2)
            self.records[key] = m
        rec.lay.addLayout(grid)
        rec.lay.addStretch(1)
        mid.addWidget(rec, 1)
        lay.addLayout(mid)

        # --- dernières parties
        recent = Card()
        hr = QHBoxLayout()
        hr.addWidget(section("Dernières parties"))
        hr.addStretch(1)
        more = QPushButton("Tout voir")
        more.setObjectName("ghost")
        more.clicked.connect(lambda: ctx.window.show_page("matches"))
        hr.addWidget(more)
        recent.lay.addLayout(hr)
        self.recent = make_table(["Date", "Mode", "Classement", "Coffres"], stretch=1)
        self.recent.horizontalHeader().setVisible(False)
        self.recent.setSelectionMode(QAbstractItemView.NoSelection)
        self.recent.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recent.lay.addWidget(self.recent)
        self.recent_empty = faint("Aucune partie pour l'instant. Lancez Fortnite avec les replays activés : "
                                  "chaque partie terminée apparaîtra ici.")
        recent.lay.addWidget(self.recent_empty)
        lay.addWidget(recent)

        self.live = LiveChip()
        self.head = header("Vue d'ensemble", "Mise à jour automatique à la fin de chaque partie", self.live)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_shell(self.head, body))

    def refresh(self, *_):
        tr = self.ctx.tracker
        s = tr.stats()
        st = tr.level()
        animate_number(self.total, s.total_chests)
        self.live.set_live(bool(self.ctx.watcher.status.recording))
        o = tr.odds()
        self.odds_pct.setText(format_percent(o.percent))
        self.odds_sub.setText(f"de chances d'avoir déjà eu le jeton, avec {fmt_int(o.openings)} ouvertures")
        self.odds_goal.setText("Vers 1 chance sur 2")
        self.odds_goal_pct.setText(f"{fmt_int(o.openings)} / {fmt_int(o.openings_for_half)}")
        self.odds_bar.set_state(0, min(1.0, o.openings / o.openings_for_half) if o.openings_for_half else 0)
        self.odds_note.setText(f"Taux publié par Epic : 1 chance sur {fmt_int(o.one_in)} par coffre (plus élevé pendant les "
                               "Treasure Hours). Chaque coffre est un tirage indépendant.")
        counted = s.total_chests - s.initial_chests
        parts = [f"{fmt_int(counted)} ouvertures comptées par Pirate Tracker",
                 f"{fmt_int(s.unique_chests)} coffres différents"]
        if s.total_reopens:
            parts.append(f"{fmt_int(s.total_reopens)} réouvertures")
        if s.initial_chests:
            parts.append(f"{fmt_int(s.initial_chests)} avant")
        if s.total_broken:
            parts.append(f"dont {fmt_int(s.total_broken)} cassés")
        if s.total_special:
            parts.append(f"{fmt_int(s.total_special)} spéciaux")
        self.total_detail.setText(" · ".join(parts))
        self.level.setText(f"Niveau {st.level}")
        self.step_lbl.setText(f"Palier {min(st.stars + 1, 5)}/5")
        self.steps.set_state(st.stars, st.star_progress)
        remaining = st.next_star_at - st.chests_in_level
        nxt = "le niveau suivant" if st.stars == 4 else f"le palier {st.stars + 2}"
        self.next_lbl.setText(f"Encore {fmt_int(remaining)} coffre{'s' if remaining > 1 else ''} avant {nxt}")

        m = self.strip.metrics
        if s.last_match_chests is None:
            m[0].set("—", "aucune partie")
        else:
            place = f" · #{s.last_match_placement}" if s.last_match_placement else ""
            m[0].set(fmt_int(s.last_match_chests), fmt_date(s.last_match_at) + place)
        m[1].set(fmt_int(s.today_chests), f"record : {fmt_int(s.best_day)}")
        avg = (counted / s.matches_count) if s.matches_count else 0
        m[2].set(f"{avg:.1f}".replace(".", ","), f"sur {fmt_int(s.matches_count)} partie{'s' if s.matches_count > 1 else ''}")
        m[3].set(fmt_int(s.since_last_token), "coffres sans jeton pirate")

        self.records["Meilleure partie"].set(fmt_int(s.best_match), "coffres")
        self.records["Meilleur jour"].set(fmt_int(s.best_day), "coffres")
        self.records["Parties analysées"].set(fmt_int(s.matches_count))
        self.records["Temps de jeu"].set(fmt_duration(s.tracked_seconds))

        counts = dict(tr.db.daily_counts(30))
        today = datetime.now().date()
        days = []
        for i in range(29, -1, -1):
            d = datetime.fromordinal(today.toordinal() - i).date()
            days.append((f"{d.day:02d}/{d.month:02d}", counts.get(d.isoformat(), 0)))
        self.chart.set_data(days)

        rows = [r for r in tr.db.matches(5)]
        self.recent.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.recent.setItem(i, 0, cell(fmt_date(r.started_at), color=T.TEXT2))
            self.recent.setItem(i, 1, cell(playlist_name(r.playlist)))
            self.recent.setItem(i, 2, cell(placement_text(r), color=T.TEXT2, tabular=True))
            self.recent.setItem(i, 3, cell(fmt_int(r.chests) if r.ok else "échec", NUM,
                                           color=T.ACCENT if r.ok and r.chests else (T.RED if not r.ok else T.TEXT2),
                                           weight=QFont.DemiBold, tabular=True))
        self.recent.setFixedHeight(42 * len(rows) + 4)
        self.recent.setVisible(bool(rows))
        self.recent_empty.setVisible(not rows)


# ---------------------------------------------------------------- parties
class MatchesPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        for text, fn in (("Exporter CSV", ctx.export_csv), ("Exporter JSON", ctx.export_json)):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.clicked.connect(fn)
            al.addWidget(b)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        card = Card(padding=8)
        self.table = make_table(["Date", "Mode", "Durée", "Classement", "Élim.", "Coffres", "Analyse"], stretch=1,
                                min_height=320)
        self.table.itemSelectionChanged.connect(self._show_detail)
        card.lay.addWidget(self.table)
        lay.addWidget(card, 3)

        self.detail = Card()
        top = QHBoxLayout()
        self.detail_title = section("Sélectionnez une partie")
        top.addWidget(self.detail_title, 1)
        self.copy_btn = QPushButton("Copier le diagnostic")
        self.copy_btn.setToolTip("Copie un résumé technique de l'analyse de cette partie, à coller dans un message")
        self.copy_btn.clicked.connect(self._copy_diag)
        top.addWidget(self.copy_btn)
        self.del_btn = QPushButton("Retirer du compteur")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self._delete)
        top.addWidget(self.del_btn)
        self.detail.lay.addLayout(top)
        self.detail_metrics = QHBoxLayout()
        self.dm = {}
        for k in ("Ouvertures", "Coffres uniques", "Cassés", "Réouvertures", "Spéciaux"):
            m = Metric(k, big=20)
            self.dm[k] = m
            self.detail_metrics.addWidget(m)
        self.detail_metrics.addStretch(1)
        self.detail.lay.addLayout(self.detail_metrics)
        self.detail_note = faint("")
        self.detail.lay.addWidget(self.detail_note)
        self.detail.lay.addWidget(caps("Déroulé de la partie"))
        self.timeline = MatchTimeline()
        self.detail.lay.addWidget(self.timeline)
        legend = QLabel(f"<span style='color:{T.ACCENT}'>●</span>&nbsp; ouvert &nbsp;&nbsp;&nbsp; "
                        f"<span style='color:{T.ACCENT}'>○</span>&nbsp; rouvert &nbsp;&nbsp;&nbsp; "
                        f"<span style='color:{T.ORANGE}'>◇</span>&nbsp; cassé")
        legend.setObjectName("faint")
        legend.setFont(T.font(11))
        self.detail.lay.addWidget(legend)
        self.detail.lay.addWidget(hline())
        self.detail.lay.addWidget(caps("Objets ramassés"))
        self.items = make_table(["Moment", "Objet", "Rareté", "Quantité"], stretch=1, min_height=200)
        self.detail.lay.addWidget(self.items)
        lay.addWidget(self.detail, 2)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_shell(header("Parties", "Chaque partie est ajoutée dès que Fortnite a écrit son replay",
                                          actions), body))
        self._rows = []

    def refresh(self, *_):
        self._rows = self.ctx.tracker.db.matches()
        self.table.setRowCount(len(self._rows))
        for i, m in enumerate(self._rows):
            self.table.setItem(i, 0, cell(fmt_date(m.started_at), color=T.TEXT2))
            self.table.setItem(i, 1, cell(playlist_name(m.playlist)))
            self.table.setItem(i, 2, cell(fmt_duration(m.duration), color=T.TEXT2, tabular=True))
            self.table.setItem(i, 3, cell(placement_text(m), color=T.ACCENT if m.placement == 1 else T.TEXT2,
                                          tabular=True))
            self.table.setItem(i, 4, cell("—" if m.eliminations is None else m.eliminations, NUM, color=T.TEXT2,
                                          tabular=True))
            self.table.setItem(i, 5, cell(fmt_int(m.chests), NUM, color=T.ACCENT if m.chests else T.TEXT2,
                                          weight=QFont.DemiBold, tabular=True))
            if not m.ok:
                st = cell("Échec", color=T.RED)
                st.setToolTip(m.error or "")
            elif m.warnings and m.chests == 0:
                st = cell("À vérifier", color=T.ORANGE)
                st.setToolTip("\n".join(m.warnings))
            elif m.warnings:
                st = cell("OK · note", color=T.TEXT2)
                st.setToolTip("\n".join(m.warnings))
            else:
                st = cell("OK", color=T.GREEN)
            self.table.setItem(i, 6, st)
        if self._rows and not self.table.selectionModel().selectedRows():
            self.table.selectRow(0)
        self._show_detail()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows and rows[0].row() < len(self._rows):
            return self._rows[rows[0].row()]
        return None

    def _show_detail(self):
        m = self._selected()
        self.detail.setVisible(m is not None)
        if m is None:
            return
        self.detail_title.setText(f"{playlist_name(m.playlist)} · {fmt_date(m.started_at)}")
        self.timeline.set_data(m.duration, self.ctx.tracker.db.match_chest_events(m.id))
        self.dm["Ouvertures"].set(fmt_int(m.chests))
        self.dm["Coffres uniques"].set(fmt_int(m.unique_chests))
        self.dm["Cassés"].set(fmt_int(m.broken))
        self.dm["Réouvertures"].set(fmt_int(m.reopens))
        self.dm["Spéciaux"].set(fmt_int(m.special))
        types = self.ctx.tracker.db.match_chest_types(m.id)
        notes = []
        if types:
            notes.append("Types : " + " · ".join(f"{items_mod.CHEST_CATEGORIES.get(cat, cat)} ×{n}" for cat, n in types))
        notes += list(m.warnings) if m.warnings else []
        if not m.ok:
            notes.insert(0, f"Replay illisible : {m.error}")
        notes.append(f"Fichier : {Path(m.replay_path).name}")
        self.detail_note.setText("\n".join(notes))
        rows = self.ctx.tracker.db.match_items(m.id)
        self.items.setRowCount(len(rows))
        for i, r in enumerate(rows):
            info = items_mod.describe(r["item"])
            t = r["ts"] - m.started_at
            self.items.setItem(i, 0, cell(f"{int(t // 60):02d}:{int(t % 60):02d}", color=T.MUTED, tabular=True))
            name = cell(info.name)
            name.setToolTip(r["item"])
            self.items.setItem(i, 1, name)
            self.items.setItem(i, 2, cell(info.rarity or "—", color=T.RARITY.get(info.rarity, T.MUTED)))
            self.items.setItem(i, 3, cell(r["count"] or 1, NUM, color=T.TEXT2, tabular=True))

    def diagnostic_text(self, m) -> str:
        """Même contenu que le journal d'analyse : à coller dans un message pour améliorer le comptage."""
        from .. import __version__
        from ..analysis_log import format_report

        d = dict(m.diagnostics or {})
        d.update(file=m.replay_path, playlist=m.playlist, duration_s=m.duration, ok=m.ok, error=m.error,
                 warnings=m.warnings, total_openings=m.chests, unique_chests=m.unique_chests,
                 broken_count=m.broken, reopen_count=m.reopens)
        return format_report(d, f"v{__version__}")

    def _copy_diag(self):
        from PySide6.QtWidgets import QApplication

        m = self._selected()
        if m:
            QApplication.clipboard().setText(self.diagnostic_text(m))
            self.ctx.toast("Diagnostic copié", "Collez-le (Ctrl+V) dans votre message")

    def _delete(self):
        m = self._selected()
        if m and QMessageBox.question(self, "Retirer la partie",
                                      "Retirer cette partie et ses coffres du compteur ?") == QMessageBox.Yes:
            self.ctx.tracker.delete_match(m.id)


# ---------------------------------------------------------------- butin
class LootPage(QWidget):
    FILTERS = [("all", "Tout"), ("arme", "Armes"), ("soin", "Soins"), ("objet", "Objets"),
               ("matériaux", "Matériaux"), ("munitions", "Munitions")]
    ORDER = ["Mythique", "Légendaire", "Épique", "Rare", "Peu commun", "Commun", ""]

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, (k, lbl) in enumerate(self.FILTERS):
            b = QPushButton(lbl)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setChecked(k == "arme")
            b.setProperty("key", k)
            self.group.addButton(b, i)
            chips.addWidget(b)
        self.group.buttonClicked.connect(self.refresh)
        chips.addStretch(1)
        self.count_lbl = faint("", wrap=False)
        chips.addWidget(self.count_lbl)
        lay.addLayout(chips)

        card = Card(padding=8)
        self.table = make_table(["Objet", "Rareté", "Obtenu", "Parties", "Première fois", ""], stretch=0,
                                min_height=420)
        card.lay.addWidget(self.table)
        lay.addWidget(card, 1)

        foot = QHBoxLayout()
        foot.addWidget(faint("Le jeton pirate est reconnu d'après le nom de l'objet. S'il n'est pas reconnu, "
                             "sélectionnez-le et marquez-le : toutes vos parties sont recalculées."), 1)
        self.mark = QPushButton("Marquer comme jeton pirate")
        self.mark.clicked.connect(lambda: self._mark(True))
        self.unmark = QPushButton("Retirer")
        self.unmark.setObjectName("ghost")
        self.unmark.clicked.connect(lambda: self._mark(False))
        foot.addWidget(self.mark)
        foot.addWidget(self.unmark)
        lay.addLayout(foot)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page_shell(header("Butin", "Tout ce que vous avez ramassé, d'après vos replays"), body))
        self._raw: list[str] = []

    def refresh(self, *_):
        tr = self.ctx.tracker
        is_token = tr.token_matcher()
        flt = self.group.checkedButton().property("key") if self.group.checkedButton() else "all"
        rows = tr.db.item_totals()
        shown = []
        for r in rows:
            info = items_mod.describe(r["item"])
            if flt != "all" and info.category != flt and not is_token(r["item"]):
                continue
            shown.append((r, info))
        shown.sort(key=lambda x: (not is_token(x[0]["item"]),
                                  self.ORDER.index(x[1].rarity) if x[1].rarity in self.ORDER else 6,
                                  -x[0]["times"]))
        self.count_lbl.setText(f"{len(rows)} objets différents")
        self._raw = []
        self.table.setRowCount(len(shown))
        for i, (r, info) in enumerate(shown):
            tok = is_token(r["item"])
            name = cell(info.name, weight=QFont.Medium if tok else None)
            name.setToolTip(r["item"])
            self.table.setItem(i, 0, name)
            self.table.setItem(i, 1, cell(info.rarity or "—", color=T.RARITY.get(info.rarity, T.MUTED)))
            self.table.setItem(i, 2, cell(f"{fmt_int(r['times'])}×", NUM, color=T.TEXT2, tabular=True))
            self.table.setItem(i, 3, cell(fmt_int(r["matches"]), NUM, color=T.TEXT2, tabular=True))
            self.table.setItem(i, 4, cell(fmt_date(r["first_ts"], with_time=False), color=T.TEXT2))
            self.table.setItem(i, 5, cell("Jeton pirate" if tok else "", color=T.ACCENT, weight=QFont.DemiBold))
            self._raw.append(r["item"])

    def _mark(self, on: bool):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, "Jeton pirate", "Sélectionnez d'abord un objet dans la liste.")
            return
        self.ctx.tracker.mark_token_item(self._raw[rows[0].row()], on)


