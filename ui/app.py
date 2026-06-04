"""
ui/app.py — StudioPhoto v2.1
Fixes: pas de setStyleSheet() inline (conflits QSS), layout propre,
       group boxes non coupées, btn_run toujours visible.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QProgressBar, QTextEdit, QLabel,
    QFrame, QSizePolicy, QStackedWidget, QScrollArea,
    QMessageBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFont

from core import config as cfg_store
from ui.grade_panel import GradePanel
from ui.rename_panel import RenamePanel
from ui.workers import GradeWorker, RenameWorker
from ui.style import QSS, ACCENT, SUCCESS, ERROR, SKIP, TEXT2, TEXT3
from version import FULL_NAME, __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._cfg = cfg_store.load()

        self.setWindowTitle(FULL_NAME)
        self.resize(1000, 720)
        self.setMinimumSize(860, 620)
        self.setStyleSheet(QSS)

        self._build_ui()
        self.grade_panel.load_config(self._cfg)
        self.rename_panel.load_config(self._cfg)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        h.addWidget(self._build_main_column(), stretch=1)

    # ── Sidebar ────────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(190)
        v = QVBoxLayout(sb)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Logo block
        logo_w = QWidget()
        lv = QVBoxLayout(logo_w)
        lv.setContentsMargins(20, 28, 20, 20)
        lv.setSpacing(4)
        logo = QLabel("STUDIO")
        logo.setObjectName("app_logo")
        ver  = QLabel(f"v{__version__}")
        ver.setObjectName("app_version")
        lv.addWidget(logo)
        lv.addWidget(ver)
        v.addWidget(logo_w)
        v.addWidget(self._hline())

        # Nav
        self.nav_grade  = QPushButton("ÉTALONNAGE")
        self.nav_rename = QPushButton("RENOMMAGE")
        for btn, name in [(self.nav_grade, "nav_grade"), (self.nav_rename, "nav_rename")]:
            btn.setObjectName(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            v.addWidget(btn)

        self.nav_grade.setChecked(True)
        self.nav_grade.clicked.connect(lambda: self._switch(0))
        self.nav_rename.clicked.connect(lambda: self._switch(1))

        v.addStretch()
        v.addWidget(self._hline())
        v.addWidget(self._build_stats_block())
        return sb

    def _build_stats_block(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 18, 20, 24)
        v.setSpacing(14)
        self.stat_processed = self._stat_row(v, "TRAITÉES")
        self.stat_skipped   = self._stat_row(v, "IGNORÉES")
        self.stat_errors    = self._stat_row(v, "ERREURS")
        return w

    def _stat_row(self, parent_layout, label_text: str) -> QLabel:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        val = QLabel("0")
        val.setObjectName("stat_value")
        val.setFont(QFont("Segoe UI", 19, QFont.Light))
        lbl = QLabel(label_text)
        lbl.setObjectName("stat_label")
        lbl.setFont(QFont("Segoe UI", 9))
        h.addWidget(val)
        h.addStretch()
        h.addWidget(lbl, alignment=Qt.AlignBottom)
        parent_layout.addWidget(row)
        return val

    # ── Main column ────────────────────────────────────────────────────────────

    def _build_main_column(self) -> QWidget:
        col = QWidget()
        col.setObjectName("content_area")
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        sc = QVBoxLayout(scroll_content)
        sc.setContentsMargins(32, 28, 32, 24)
        sc.setSpacing(0)

        self.stack = QStackedWidget()
        self.grade_panel  = GradePanel()
        self.rename_panel = RenamePanel()
        self.stack.addWidget(self.grade_panel)
        self.stack.addWidget(self.rename_panel)
        sc.addWidget(self.stack)
        sc.addStretch()

        scroll.setWidget(scroll_content)
        v.addWidget(scroll, stretch=1)

        # Action bar — widget dédié avec objectName pour le QSS
        v.addWidget(self._build_action_bar())

        # Progress card (masqué par défaut)
        self.progress_card = self._build_progress_card()
        self.progress_card.setVisible(False)
        v.addWidget(self.progress_card)

        # Console
        self.console = QTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(150)
        self.console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.console, stretch=1)

        return col

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("action_bar")
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.setFixedHeight(62)

        h = QHBoxLayout(bar)
        h.setContentsMargins(32, 12, 32, 12)
        h.setSpacing(10)

        self.btn_run = QPushButton("▶   LANCER")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setCursor(Qt.PointingHandCursor)

        self.btn_cancel = QPushButton("ANNULER")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)

        self.btn_run.clicked.connect(self._on_run)
        self.btn_cancel.clicked.connect(self._on_cancel)

        self.lbl_speed = QLabel("")
        self.lbl_speed.setFont(QFont("Segoe UI", 10))

        h.addWidget(self.btn_run)
        h.addWidget(self.btn_cancel)
        h.addStretch()
        h.addWidget(self.lbl_speed)
        return bar

    def _build_progress_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("progress_card")
        v = QVBoxLayout(card)
        v.setContentsMargins(32, 12, 32, 12)
        v.setSpacing(6)

        # Ligne 1 : dossier + ETA
        row1 = QHBoxLayout()
        folder_ico = QLabel("▸")
        folder_ico.setFont(QFont("Segoe UI", 11))
        self.lbl_folder = QLabel("—")
        self.lbl_folder.setObjectName("progress_folder")
        self.lbl_eta = QLabel("")
        self.lbl_eta.setFont(QFont("Segoe UI", 10))

        row1.addWidget(folder_ico)
        row1.addWidget(self.lbl_folder)
        row1.addStretch()
        row1.addWidget(self.lbl_eta)
        v.addLayout(row1)

        # Barre de progression 2px
        self.progress = QProgressBar()
        self.progress.setObjectName("progress_bar")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(2)
        v.addWidget(self.progress)

        # Ligne 2 : fichier + compteur + %
        row2 = QHBoxLayout()
        self.lbl_file    = QLabel("—")
        self.lbl_file.setObjectName("progress_file")
        self.lbl_counter = QLabel("")
        self.lbl_counter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        self.lbl_pct = QLabel("")
        self.lbl_pct.setFont(QFont("Segoe UI", 10))

        row2.addWidget(self.lbl_file)
        row2.addStretch()
        row2.addWidget(self.lbl_counter)
        row2.addWidget(self.lbl_pct)
        v.addLayout(row2)

        return card

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _switch(self, idx: int) -> None:
        self.stack.setCurrentIndex(idx)
        self.nav_grade.setChecked(idx == 0)
        self.nav_rename.setChecked(idx == 1)

    # ── Run / Cancel ──────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        if self.stack.currentIndex() == 0:
            self._start_grading()
        else:
            self._start_renaming()

    def _start_grading(self) -> None:
        params = self.grade_panel.get_params()
        if not params["folder"] or not params["folder"].is_dir():
            QMessageBox.critical(self, "Erreur", "Choisis un dossier source valide.")
            return

        self._log_sep()
        self._log(f"  Source    : {params['folder']}", TEXT2)
        self._log(f"  Sortie    : {params['output_dir'] or '_output (par dossier)'}", TEXT2)
        self._log(
            f"  Processus : {params['workers']}  ·  Suffixe : {params['suffix']}  ·  "
            f"Récursif : {'oui' if params['recursive'] else 'non'}", TEXT2
        )

        worker = GradeWorker(params)
        worker.log_line.connect(self._log_auto)
        worker.progress.connect(self._update_progress)
        worker.current.connect(self._update_current)
        worker.speed.connect(self._update_speed)
        worker.eta.connect(self._update_eta)
        worker.finished.connect(self._on_grade_done)
        self._start_worker(worker)

    def _start_renaming(self) -> None:
        params = self.rename_panel.get_params()
        if not params["base"] or not params["base"].is_dir():
            QMessageBox.critical(self, "Erreur", "Choisis un dossier de base valide.")
            return

        if not params["dry_run"]:
            reply = QMessageBox.question(
                self, "Confirmer le renommage",
                "Le renommage modifie les fichiers de façon irréversible.\n\nContinuer ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._log_sep()
        mode = "APERÇU" if params["dry_run"] else "RENOMMAGE RÉEL"
        self._log(f"  Mode : {mode}  ·  Base : {params['base']}", TEXT2)

        worker = RenameWorker(params)
        worker.log_line.connect(self._log_auto)
        worker.progress.connect(self._update_progress)
        worker.current.connect(self._update_current)
        worker.finished.connect(self._on_rename_done)
        self._start_worker(worker)

    def _start_worker(self, worker) -> None:
        self._worker = worker
        self._reset_stats()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_speed.setText("")
        self.progress.setValue(0)
        self.progress.setMaximum(1)
        self.lbl_folder.setText("Démarrage…")
        self.lbl_file.setText("")
        self.lbl_counter.setText("")
        self.lbl_pct.setText("")
        self.lbl_eta.setText("")
        self.progress_card.setVisible(True)
        worker.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._log("  ⏹ Annulation demandée…", TEXT3)

    # ── Progress callbacks ────────────────────────────────────────────────────

    def _update_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        if total > 0:
            pct = int(done / total * 100)
            self.lbl_counter.setText(f"{done} / {total}")
            self.lbl_pct.setText(f"  {pct} %")

    def _update_current(self, folder: str, file: str) -> None:
        if folder:
            self.lbl_folder.setText(folder)
        if file:
            self.lbl_file.setText(file)

    def _update_speed(self, speed: float) -> None:
        if speed > 0:
            self.lbl_speed.setText(f"{speed:.1f} img/s")

    def _update_eta(self, eta: int) -> None:
        if eta > 0:
            m, s = divmod(eta, 60)
            self.lbl_eta.setText(f"~{m}:{s:02d}" if m else f"~{s}s")
        else:
            self.lbl_eta.setText("")

    # ── Finish callbacks ──────────────────────────────────────────────────────

    def _on_grade_done(self, result: dict) -> None:
        self.stat_processed.setText(str(result["ok"]))
        self.stat_skipped.setText(str(result["skipped"]))
        self.stat_errors.setText(str(result["errors"]))

        self._log_sep()
        status = "Annulé" if result.get("cancelled") else "Terminé"
        parts  = [f"{result['ok']} traitée(s)"]
        if result["skipped"]:  parts.append(f"{result['skipped']} ignorée(s)")
        if result["errors"]:   parts.append(f"{result['errors']} erreur(s)")
        self._log(f"  {status}  ·  " + "  ·  ".join(parts), ACCENT)
        self._log_sep()
        self._finish()

    def _on_rename_done(self, total_renamed: int, dry_run: bool) -> None:
        self._log_sep()
        verb = "à renommer (aperçu)" if dry_run else "renommée(s)"
        self._log(f"  Terminé  ·  {total_renamed} image(s) {verb}.", ACCENT)
        self._log_sep()
        self._finish()

    def _finish(self) -> None:
        self._worker = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_file.setText("Terminé")
        self.lbl_eta.setText("")
        QTimer.singleShot(4000, lambda: self.progress_card.setVisible(False))

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log_auto(self, text: str) -> None:
        if "✓" in text:   self._log(text, SUCCESS)
        elif "✗" in text: self._log(text, ERROR)
        elif "⏭" in text: self._log(text, SKIP)
        else:              self._log(text, TEXT2)

    def _log(self, text: str, color: str = TEXT2) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cur = self.console.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText(text + "\n", fmt)
        self.console.setTextCursor(cur)
        self.console.ensureCursorVisible()

    def _log_sep(self) -> None:
        self._log("─" * 72, "#252525")

    def _reset_stats(self) -> None:
        self.stat_processed.setText("0")
        self.stat_skipped.setText("0")
        self.stat_errors.setText("0")

    # ── Persist ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.grade_panel.save_config(self._cfg)
        self.rename_panel.save_config(self._cfg)
        cfg_store.save(self._cfg)
        super().closeEvent(event)

    @staticmethod
    def _hline() -> QFrame:
        f = QFrame()
        f.setObjectName("hline")
        f.setFrameShape(QFrame.HLine)
        f.setFixedHeight(1)
        return f
