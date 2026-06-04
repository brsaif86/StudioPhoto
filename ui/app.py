"""
ui/app.py — StudioPhoto v2 — Dark professional interface
=========================================================
Aesthetic: Capture One × DaVinci Resolve
Layout: sidebar nav · content panel · progress card · log console
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QProgressBar, QTextEdit, QLabel,
    QFrame, QSizePolicy, QStackedWidget, QSpacerItem,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QTextCharFormat, QTextCursor

from core import config as cfg_store
from ui.grade_panel import GradePanel
from ui.rename_panel import RenamePanel
from ui.workers import GradeWorker, RenameWorker
from ui.style import QSS, ACCENT, SUCCESS, ERROR, SKIP, TEXT2, TEXT3, BG2
from version import FULL_NAME, __version__


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._cfg = cfg_store.load()
        self._done = 0
        self._total = 0
        self._speed = 0.0

        self.setWindowTitle(FULL_NAME)
        self.resize(940, 700)
        self.setMinimumSize(820, 600)
        self.setStyleSheet(QSS)

        self._build_ui()
        self.grade_panel.load_config(self._cfg)
        self.rename_panel.load_config(self._cfg)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main(), stretch=1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Logo
        logo = QLabel("STUDIO")
        logo.setObjectName("app_logo")
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("app_version")
        v.addWidget(logo)
        v.addWidget(ver)

        # Separator
        v.addWidget(self._hline())

        # Nav buttons
        self.nav_grade  = QPushButton("ÉTALONNAGE")
        self.nav_rename = QPushButton("RENOMMAGE")
        for btn in (self.nav_grade, self.nav_rename):
            btn.setCheckable(True)
            btn.setObjectName(f"nav_{'grade' if btn is self.nav_grade else 'rename'}")
            btn.setCursor(Qt.PointingHandCursor)
            v.addWidget(btn)

        self.nav_grade.setChecked(True)
        self.nav_grade.clicked.connect(lambda: self._switch(0))
        self.nav_rename.clicked.connect(lambda: self._switch(1))

        v.addStretch()

        # Stats at bottom of sidebar
        v.addWidget(self._hline())
        v.addWidget(self._build_sidebar_stats())

        return sidebar

    def _build_sidebar_stats(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 20)
        v.setSpacing(12)

        for attr, val_text, lbl_text in (
            ("stat_processed", "0", "TRAITÉES"),
            ("stat_skipped",   "0", "IGNORÉES"),
            ("stat_errors",    "0", "ERREURS"),
        ):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            val = QLabel(val_text)
            val.setObjectName("stat_value")
            val.setFont(QFont("Segoe UI", 18, QFont.Light))
            lbl = QLabel(lbl_text)
            lbl.setObjectName("stat_label")
            lbl.setFont(QFont("Segoe UI", 9))
            h.addWidget(val)
            h.addStretch()
            h.addWidget(lbl, alignment=Qt.AlignBottom)
            v.addWidget(row)
            setattr(self, attr, val)

        return w

    def _build_main(self) -> QWidget:
        main = QWidget()
        v = QVBoxLayout(main)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── Content panels ───────────────────────────────────────────────────
        self.stack = QStackedWidget()
        self.grade_panel  = GradePanel()
        self.rename_panel = RenamePanel()
        self.stack.addWidget(self.grade_panel)
        self.stack.addWidget(self.rename_panel)

        content_wrap = QWidget()
        cw = QVBoxLayout(content_wrap)
        cw.setContentsMargins(28, 24, 28, 20)
        cw.addWidget(self.stack)
        cw.addStretch()

        # ── Action bar ────────────────────────────────────────────────────────
        action_bar = self._build_action_bar()

        # ── Progress card ────────────────────────────────────────────────────
        self.progress_card = self._build_progress_card()
        self.progress_card.setVisible(False)

        # ── Log console ───────────────────────────────────────────────────────
        self.console = QTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(160)
        self.console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        v.addWidget(content_wrap, stretch=0)
        v.addWidget(action_bar)
        v.addWidget(self.progress_card)
        v.addWidget(self.console, stretch=1)

        return main

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background-color: #0F0F0F; border-top: 1px solid #1E1E1E;")
        h = QHBoxLayout(bar)
        h.setContentsMargins(28, 12, 28, 12)
        h.setSpacing(10)

        self.btn_run    = QPushButton("▶   LANCER")
        self.btn_cancel = QPushButton("ANNULER")
        self.btn_run.setObjectName("btn_run")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_run.setFixedHeight(38)
        self.btn_cancel.setFixedHeight(38)

        self.btn_run.clicked.connect(self._on_run)
        self.btn_cancel.clicked.connect(self._on_cancel)

        h.addWidget(self.btn_run)
        h.addWidget(self.btn_cancel)
        h.addStretch()

        # Inline speed indicator
        self.lbl_speed = QLabel("")
        self.lbl_speed.setStyleSheet(f"color: {TEXT3}; font-size: 11px;")
        h.addWidget(self.lbl_speed)

        return bar

    def _build_progress_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"background-color: {BG2}; border-bottom: 1px solid #1E1E1E;")
        v = QVBoxLayout(card)
        v.setContentsMargins(28, 14, 28, 14)
        v.setSpacing(8)

        # Top row: folder + ETA
        top = QHBoxLayout()
        folder_icon = QLabel("📁")
        folder_icon.setStyleSheet("font-size: 12px;")
        self.lbl_folder = QLabel("—")
        self.lbl_folder.setObjectName("progress_folder")
        top.addWidget(folder_icon)
        top.addWidget(self.lbl_folder)
        top.addStretch()
        self.lbl_eta = QLabel("")
        self.lbl_eta.setStyleSheet(f"color: {TEXT3}; font-size: 11px;")
        top.addWidget(self.lbl_eta)
        v.addLayout(top)

        # Progress bar (thin)
        self.progress = QProgressBar()
        self.progress.setObjectName("progress_thin")
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        v.addWidget(self.progress)

        # Bottom row: file + counter
        bottom = QHBoxLayout()
        self.lbl_file = QLabel("—")
        self.lbl_file.setObjectName("progress_file")
        bottom.addWidget(self.lbl_file)
        bottom.addStretch()
        self.lbl_counter = QLabel("")
        self.lbl_counter.setStyleSheet(f"color: {TEXT2}; font-size: 12px; font-weight: 600;")
        self.lbl_pct = QLabel("")
        self.lbl_pct.setStyleSheet(f"color: {TEXT3}; font-size: 11px; margin-left: 8px;")
        bottom.addWidget(self.lbl_counter)
        bottom.addWidget(self.lbl_pct)
        v.addLayout(bottom)

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
        from PySide6.QtWidgets import QMessageBox
        params = self.grade_panel.get_params()
        if not params["folder"] or not params["folder"].is_dir():
            QMessageBox.critical(self, "Erreur", "Choisis un dossier source valide.")
            return

        self._log_sep()
        self._log(f"  Source    : {params['folder']}", TEXT2)
        self._log(f"  Sortie    : {params['output_dir'] or '_output (par dossier)'}", TEXT2)
        self._log(
            f"  Processus : {params['workers']}  ·  "
            f"Suffixe : {params['suffix']}  ·  "
            f"Récursif : {'oui' if params['recursive'] else 'non'}",
            TEXT2
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
        from PySide6.QtWidgets import QMessageBox
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
        self._done = 0
        self._total = 0
        self._reset_stats()
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setMaximum(1)
        self.progress_card.setVisible(True)
        self.lbl_folder.setText("Démarrage…")
        self.lbl_file.setText("")
        self.lbl_counter.setText("")
        self.lbl_pct.setText("")
        self.lbl_eta.setText("")
        self.lbl_speed.setText("")
        worker.start()

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._log("  ⏹ Annulation demandée…", TEXT3)

    # ── Progress callbacks ────────────────────────────────────────────────────

    def _update_progress(self, done: int, total: int) -> None:
        self._done = done
        self._total = total
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        if total > 0:
            pct = int(done / total * 100)
            self.lbl_counter.setText(f"{done} / {total}")
            self.lbl_pct.setText(f"{pct}%")

    def _update_current(self, folder: str, file: str) -> None:
        if folder:
            self.lbl_folder.setText(folder)
        if file:
            self.lbl_file.setText(file)

    def _update_speed(self, speed: float) -> None:
        self._speed = speed
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
        if result["skipped"]:
            parts.append(f"{result['skipped']} ignorée(s)")
        if result["errors"]:
            parts.append(f"{result['errors']} erreur(s)")
        self._log(f"  {status} · " + "  ·  ".join(parts), ACCENT)
        self._log_sep()
        self._finish()

    def _on_rename_done(self, total_renamed: int, dry_run: bool) -> None:
        self._log_sep()
        verb = "à renommer (aperçu)" if dry_run else "renommée(s)"
        self._log(f"  Terminé · {total_renamed} image(s) {verb}.", ACCENT)
        self._log_sep()
        self._finish()

    def _finish(self) -> None:
        self._worker = None
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_eta.setText("")
        self.lbl_file.setText("Terminé")
        QTimer.singleShot(3000, lambda: self.progress_card.setVisible(False))

    # ── Logging helpers ───────────────────────────────────────────────────────

    def _log_auto(self, text: str) -> None:
        """Détecte la nature du message et colore en conséquence."""
        if "✓" in text:
            self._log(text, SUCCESS)
        elif "✗" in text:
            self._log(text, ERROR)
        elif "⏭" in text:
            self._log(text, SKIP)
        else:
            self._log(text, TEXT2)

    def _log(self, text: str, color: str = TEXT2) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)
        self.console.setTextCursor(cursor)
        self.console.ensureCursorVisible()

    def _log_sep(self) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#2A2A2A"))
        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("─" * 64 + "\n", fmt)
        self.console.setTextCursor(cursor)

    def _reset_stats(self) -> None:
        self.stat_processed.setText("0")
        self.stat_skipped.setText("0")
        self.stat_errors.setText("0")

    # ── Persist config ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self.grade_panel.save_config(self._cfg)
        self.rename_panel.save_config(self._cfg)
        cfg_store.save(self._cfg)
        super().closeEvent(event)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        return line
