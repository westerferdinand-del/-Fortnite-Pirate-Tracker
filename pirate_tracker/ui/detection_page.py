"""Page Détection : état, calibrage (invite « Fouiller » / jeton), diagnostic en direct, test sur vidéo."""
from __future__ import annotations

import threading
from collections import deque

import cv2
import numpy as np
from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from ..capture import CaptureError, create_capture
from ..detection.common import WORK_WIDTH
from ..detection.templates import imread_unicode
from ..detection.token import TOKEN_WORK_WIDTH
from ..engine import analyze_video
from . import theme as T
from .pages import scroll_page
from .widgets import Card, StatusPill, h1, h2, muted


def to_qimage(bgr: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class CropView(QWidget):
    """Affiche une image ; l'utilisateur trace un rectangle à la souris."""

    def __init__(self, img: np.ndarray, parent=None):
        super().__init__(parent)
        self.img = img
        self.qimg = to_qimage(img)
        self.sel: QRectF | None = None
        self._start: QPointF | None = None
        self.setMinimumSize(900, 520)
        self.setCursor(Qt.CrossCursor)

    def _geom(self):
        iw, ih = self.qimg.width(), self.qimg.height()
        k = min(self.width() / iw, self.height() / ih)
        ox, oy = (self.width() - iw * k) / 2, (self.height() - ih * k) / 2
        return k, ox, oy

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.BG))
        k, ox, oy = self._geom()
        target = QRectF(ox, oy, self.qimg.width() * k, self.qimg.height() * k)
        p.drawImage(target, self.qimg)
        if self.sel:
            p.fillRect(target, QColor(0, 0, 0, 110))
            src = QRectF(self.sel.x(), self.sel.y(), self.sel.width(), self.sel.height())
            dst = QRectF(ox + src.x() * k, oy + src.y() * k, src.width() * k, src.height() * k)
            p.drawImage(dst, self.qimg, src)
            p.setPen(QPen(QColor(T.GOLD), 2, Qt.DashLine))
            p.drawRect(dst)
        p.end()

    def _to_img(self, pos) -> QPointF:
        k, ox, oy = self._geom()
        x = min(max((pos.x() - ox) / k, 0), self.qimg.width() - 1)
        y = min(max((pos.y() - oy) / k, 0), self.qimg.height() - 1)
        return QPointF(x, y)

    def mousePressEvent(self, e):
        self._start = self._to_img(e.position())
        self.sel = None
        self.update()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self.sel = QRectF(self._start, self._to_img(e.position())).normalized()
            self.update()

    def mouseReleaseEvent(self, e):
        self._start = None

    def selection(self) -> QRect | None:
        if not self.sel or self.sel.width() < 8 or self.sel.height() < 8:
            return None
        return self.sel.toRect()


class CropDialog(QDialog):
    def __init__(self, img: np.ndarray, title: str, help_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1200, 760)
        lay = QVBoxLayout(self)
        lay.addWidget(h2(title))
        lay.addWidget(muted(help_text))
        self.view = CropView(img)
        lay.addWidget(self.view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Enregistrer le modèle")
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Annuler")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.rect = None

    def _ok(self):
        self.rect = self.view.selection()
        if self.rect is None:
            QMessageBox.information(self, "Sélection", "Tracez un rectangle autour de l'élément à reconnaître.")
            return
        self.accept()


class LiveGraph(QWidget):
    """Courbes temps réel des scores de détection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.prompt = deque(maxlen=240)
        self.burst = deque(maxlen=240)
        self.events = deque(maxlen=240)
        self.threshold = 0.72
        self.setMinimumHeight(170)

    def push(self, m: dict, event: bool = False):
        self.prompt.append(float(m.get("prompt", 0)))
        self.burst.append(min(3.0, float(m.get("burst", 0))) / 3.0)
        self.events.append(event)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(T.BORDER), 1))
        p.setBrush(QColor(T.BG2))
        p.drawRoundedRect(r, 10, 10)
        plot = r.adjusted(10, 10, -10, -22)
        y_thr = plot.bottom() - plot.height() * self.threshold
        p.setPen(QPen(T.c(T.VIOLET, 140), 1, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), y_thr), QPointF(plot.right(), y_thr))
        y_b = plot.bottom() - plot.height() / 3.0
        p.setPen(QPen(T.c(T.GOLD, 120), 1, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), y_b), QPointF(plot.right(), y_b))
        n = self.prompt.maxlen
        for series, color in ((self.prompt, T.VIOLET), (self.burst, T.GOLD)):
            if len(series) < 2:
                continue
            path = QPainterPath()
            off = n - len(series)
            for i, v in enumerate(series):
                pt = QPointF(plot.left() + plot.width() * (off + i) / (n - 1), plot.bottom() - plot.height() * v)
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            p.setPen(QPen(QColor(color), 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        off = n - len(self.events)
        for i, ev in enumerate(self.events):
            if ev:
                x = plot.left() + plot.width() * (off + i) / (n - 1)
                p.setPen(QPen(QColor(T.GREEN), 2))
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        p.setFont(T.ui_font(8))
        p.setPen(QColor(T.VIOLET))
        p.drawText(QRectF(plot.left(), plot.bottom() + 4, 200, 16), Qt.AlignLeft, "— invite « Fouiller »")
        p.setPen(QColor(T.GOLD))
        p.drawText(QRectF(plot.left() + 170, plot.bottom() + 4, 200, 16), Qt.AlignLeft, "— éclat d'ouverture")
        p.setPen(QColor(T.GREEN))
        p.drawText(QRectF(plot.left() + 340, plot.bottom() + 4, 200, 16), Qt.AlignLeft, "| coffre compté")
        p.end()


class _VideoWorker(QObject):
    progress = Signal(float)
    done = Signal(object)

    def __init__(self, path, settings, templates):
        super().__init__()
        self.path, self.settings, self.templates = path, dict(settings), templates
        self.stop = threading.Event()

    def run(self):
        try:
            res = analyze_video(self.path, self.settings, self.templates, progress=self.progress.emit, stop=self.stop)
        except Exception as e:  # noqa: BLE001
            res = {"error": str(e)}
        self.done.emit(res)


class TemplateList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QPixmap(150, 60).size())
        self.setResizeMode(QListWidget.Adjust)
        self.setFixedHeight(100)
        self.setStyleSheet(f"QListWidget {{ background: {T.BG2}; border: 1px solid {T.BORDER}; border-radius: 10px; }}")


class DetectionPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(h1("DÉTECTION AUTOMATIQUE"), 1)
        self.status = StatusPill()
        top.addWidget(self.status)
        lay.addLayout(top)

        # --- état
        st = Card()
        sl = QGridLayout(st)
        sl.setContentsMargins(20, 16, 20, 16)
        self.lbl_msg = QLabel("—")
        self.lbl_msg.setFont(T.ui_font(10, QFont.Bold))
        self.lbl_msg.setWordWrap(True)
        self.lbl_fortnite = muted("Fortnite : —")
        self.lbl_capture = muted("Capture : —")
        self.lbl_mode = muted("Mode : —")
        self.lbl_state = muted("État : —")
        sl.addWidget(self.lbl_msg, 0, 0, 1, 4)
        for i, w in enumerate((self.lbl_fortnite, self.lbl_capture, self.lbl_mode, self.lbl_state)):
            sl.addWidget(w, 1, i)
        lay.addWidget(st)

        # --- calibrage invite
        cal = Card()
        cl = QVBoxLayout(cal)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.addWidget(h2("1. Calibrage de l'invite « Fouiller » (recommandé, une seule fois)"))
        cl.addWidget(muted(
            "Placez-vous devant un coffre fermé pour que l'invite « [E] Fouiller — Coffre » s'affiche, puis capturez "
            "l'écran et entourez l'invite EN INCLUANT le mot « Coffre » (cela évite de compter les caisses de "
            "munitions). Capturez 2 ou 3 exemples sur des fonds différents pour plus de fiabilité. "
            "Sans calibrage, l'application utilise le mode « éclat seul », moins fiable."))
        self.prompt_list = TemplateList()
        cl.addWidget(self.prompt_list)
        row = QHBoxLayout()
        b1 = QPushButton("Capturer l'écran dans 5 s")
        b1.setObjectName("primary")
        b1.clicked.connect(lambda: self._countdown_capture("prompt"))
        b2 = QPushButton("Importer une capture d'écran…")
        b2.clicked.connect(lambda: self._import("prompt"))
        b3 = QPushButton("Supprimer la sélection")
        b3.setObjectName("danger")
        b3.clicked.connect(lambda: self._remove("prompt"))
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        cl.addLayout(row)
        lay.addWidget(cal)

        # --- calibrage jeton
        tok = Card()
        tl = QVBoxLayout(tok)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.addWidget(h2("2. Modèle du jeton pirate"))
        tl.addWidget(muted(
            "Fournissez une capture où le jeton pirate est visible (ramassage, inventaire ou notification) et "
            "entourez précisément l'icône. Le jeton n'est reconnu que si la forme, les couleurs et le détail "
            "correspondent, sur plusieurs images consécutives : une image simplement ressemblante est rejetée."))
        self.token_list = TemplateList()
        tl.addWidget(self.token_list)
        row = QHBoxLayout()
        b1 = QPushButton("Capturer l'écran dans 5 s")
        b1.setObjectName("gold")
        b1.clicked.connect(lambda: self._countdown_capture("token"))
        b2 = QPushButton("Importer une image…")
        b2.clicked.connect(lambda: self._import("token"))
        b3 = QPushButton("Supprimer la sélection")
        b3.setObjectName("danger")
        b3.clicked.connect(lambda: self._remove("token"))
        for b in (b1, b2, b3):
            row.addWidget(b)
        row.addStretch(1)
        tl.addLayout(row)
        lay.addWidget(tok)

        # --- diagnostic en direct
        dg = Card()
        dl = QVBoxLayout(dg)
        dl.setContentsMargins(20, 16, 20, 16)
        dl.addWidget(h2("3. Diagnostic en direct"))
        dl.addWidget(muted("Pendant une partie, la courbe violette doit dépasser la ligne pointillée quand l'invite "
                           "est visible, et la courbe dorée monter à l'ouverture du coffre. Ajustez la sensibilité "
                           "dans les Paramètres si nécessaire."))
        self.graph = LiveGraph()
        dl.addWidget(self.graph)
        row = QHBoxLayout()
        self.lbl_live = muted("", wrap=False)
        row.addWidget(self.lbl_live, 1)
        undo = QPushButton("Annuler le dernier coffre (faux positif)")
        undo.setObjectName("danger")
        undo.clicked.connect(self._undo)
        row.addWidget(undo)
        dl.addLayout(row)
        lay.addWidget(dg)

        # --- test vidéo
        vd = Card()
        vl = QVBoxLayout(vd)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.addWidget(h2("4. Tester la détection sur une vidéo"))
        vl.addWidget(muted("Enregistrez une partie (Xbox Game Bar : Win + Alt + R, ou OBS), puis analysez-la ici "
                           "pour vérifier que chaque ouverture de coffre est bien comptée avant de jouer pour de vrai."))
        row = QHBoxLayout()
        self.btn_video = QPushButton("Analyser une vidéo…")
        self.btn_video.setObjectName("primary")
        self.btn_video.clicked.connect(self._analyze_video)
        row.addWidget(self.btn_video)
        self.video_progress = QProgressBar()
        self.video_progress.setRange(0, 100)
        self.video_progress.setVisible(False)
        row.addWidget(self.video_progress, 1)
        vl.addLayout(row)
        self.video_result = muted("")
        self.video_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        vl.addWidget(self.video_result)
        lay.addWidget(vd)
        lay.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(inner))
        self._thread = None
        self._chest_flag = False
        self.refresh_templates()

    # ------------------------------------------------------------------ status / metrics
    def set_status(self, status):
        self.status.set_status(status.level, status.message)
        self.lbl_msg.setText(status.message)
        fg = "" if status.fortnite_foreground is None else (" · au premier plan" if status.fortnite_foreground else " · arrière-plan")
        self.lbl_fortnite.setText(f"Fortnite : {'lancé' + fg if status.fortnite_running else 'non détecté'}")
        self.lbl_capture.setText(f"Capture : {status.backend or '—'} · {status.fps:.0f} img/s")
        mode = {"prompt+burst": "invite + éclat (fiable)", "burst": "éclat seul (repli)"}.get(status.chest_mode, "—")
        self.lbl_mode.setText(f"Mode : {mode}")

    def on_metrics(self, m: dict):
        if not self.isVisible():
            self._chest_flag = False
            return
        self.graph.threshold = float(self.ctx.config.get("detection", "prompt_threshold", 0.72))
        self.graph.push(m, self._chest_flag)
        self._chest_flag = False
        self.lbl_state.setText(f"État : {m.get('state', '—')}")
        tok = m.get("token") or {}
        self.lbl_live.setText(f"Invite {m.get('prompt', 0):.2f} · éclat {m.get('burst', 0):.2f} · "
                              f"or {m.get('gold', 0) * 100:.1f} % · jeton {tok.get('shape', 0):.2f}")

    def on_chest(self):
        self._chest_flag = True

    # ------------------------------------------------------------------ templates
    def refresh_templates(self):
        for kind, lst in (("prompt", self.prompt_list), ("token", self.token_list)):
            lst.clear()
            for path in self.ctx.templates.list(kind):
                img = imread_unicode(path)
                if img is None:
                    continue
                pm = QPixmap.fromImage(to_qimage(img)).scaled(150, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                it = QListWidgetItem(pm, "")
                it.setData(Qt.UserRole, str(path))
                it.setToolTip(path.name)
                lst.addItem(it)
            if lst.count() == 0:
                it = QListWidgetItem("Aucun modèle — à capturer")
                it.setFlags(Qt.NoItemFlags)
                lst.addItem(it)

    def _remove(self, kind):
        lst = self.prompt_list if kind == "prompt" else self.token_list
        for it in lst.selectedItems():
            p = it.data(Qt.UserRole)
            if p:
                self.ctx.templates.remove(p)
        self.refresh_templates()
        self.ctx.engine.reload()

    def _countdown_capture(self, kind):
        win = self.window()
        self._count = 5
        self._kind = kind
        win.showMinimized()
        self.ctx.toast("eye", "Calibrage", "Capture dans 5 secondes : affichez Fortnite !")
        QTimer.singleShot(5000, self._do_capture)

    def _do_capture(self):
        frame = None
        try:
            cap = create_capture(self.ctx.config.get("detection", "capture_backend", "auto"),
                                 int(self.ctx.config.get("detection", "monitor", 1)))
            frame = cap.grab()
            cap.close()
        except CaptureError as e:
            QMessageBox.warning(self, "Capture impossible", str(e))
        win = self.window()
        win.showNormal()
        win.raise_()
        win.activateWindow()
        if frame is not None:
            self._crop_and_save(self._kind, frame)

    def _import(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une capture d'écran", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            img = imread_unicode(path)
            if img is None:
                QMessageBox.warning(self, "Image illisible", path)
                return
            self._crop_and_save(kind, img)

    def _crop_and_save(self, kind, img):
        if kind == "prompt":
            title = "Entourez l'invite « Fouiller — Coffre »"
            help_text = "Incluez la touche, le mot « Fouiller » et le libellé « Coffre ». Évitez trop de décor autour."
        else:
            title = "Entourez l'icône du jeton pirate"
            help_text = "Tracez un rectangle serré autour du jeton (le moins de fond possible)."
        dlg = CropDialog(img, title, help_text, self)
        if dlg.exec() != QDialog.Accepted or dlg.rect is None:
            return
        r = dlg.rect
        crop = img[r.y():r.y() + r.height(), r.x():r.x() + r.width()]
        H, W = img.shape[:2]
        k = (WORK_WIDTH if kind == "prompt" else TOKEN_WORK_WIDTH) / float(W)
        tpl = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        self.ctx.templates.add(kind, tpl)
        if kind == "prompt":
            # Zone de recherche = rectangle élargi autour de l'invite (rapide et moins de faux positifs)
            mx, my = r.width() * 0.6, r.height() * 1.2
            x0, y0 = max(0.0, (r.x() - mx) / W), max(0.0, (r.y() - my) / H)
            x1, y1 = min(1.0, (r.right() + mx) / W), min(1.0, (r.bottom() + my) / H)
            prev = self.ctx.config.get("detection", "prompt_roi")
            if self.ctx.templates.count("prompt") > 1 and prev:
                x0, y0 = min(x0, prev[0]), min(y0, prev[1])
                x1, y1 = max(x1, prev[0] + prev[2]), max(y1, prev[1] + prev[3])
            self.ctx.config.set("detection", "prompt_roi", [round(x0, 4), round(y0, 4), round(x1 - x0, 4), round(y1 - y0, 4)])
            if self.ctx.config.get("detection", "chest_mode") == "burst":
                self.ctx.config.set("detection", "chest_mode", "prompt+burst")
        self.refresh_templates()
        self.ctx.engine.reload()
        self.ctx.toast("star", "Modèle enregistré", "La détection utilise maintenant ce modèle.")

    # ------------------------------------------------------------------ misc
    def _undo(self):
        if self.ctx.tracker.undo_last_chest():
            self.ctx.toast("chest", "Correction", "Dernier coffre retiré du compteur.")

    def _analyze_video(self):
        if self._thread is not None:
            self._worker.stop.set()
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une vidéo de partie", "",
                                              "Vidéos (*.mp4 *.mkv *.avi *.mov *.webm)")
        if not path:
            return
        self._worker = _VideoWorker(path, self.ctx.config.section("detection"), self.ctx.templates)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda v: self.video_progress.setValue(int(v * 100)))
        self._worker.done.connect(self._video_done)
        self.video_progress.setVisible(True)
        self.video_progress.setValue(0)
        self.btn_video.setText("Arrêter l'analyse")
        self.video_result.setText("Analyse en cours…")
        self._thread.start()

    def _video_done(self, res):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.video_progress.setVisible(False)
        self.btn_video.setText("Analyser une vidéo…")
        if "error" in res:
            self.video_result.setText(f"Erreur : {res['error']}")
            return

        def mmss(t):
            return f"{int(t // 60):02d}:{t % 60:04.1f}"

        chests = ", ".join(mmss(c["t"]) for c in res["chests"]) or "aucun"
        toks = ", ".join(mmss(c["t"]) for c in res["tokens"]) or "aucun"
        mode = "invite + éclat" if res["mode"] == "prompt+burst" else "éclat seul (aucun modèle d'invite)"
        self.video_result.setText(
            f"<b style='color:{T.GOLD}'>{len(res['chests'])} coffre(s) détecté(s)</b> en mode {mode} "
            f"({res['frames']} images analysées).<br>Instants : {chests}<br>Jetons : {toks}<br>"
            "Comparez avec la vidéo : chaque instant doit correspondre à une ouverture réelle.")
