"""
ui/app.py — Fenêtre principale PySide6
=======================================
L'UI ne fait qu'appeler le core et afficher la progression.
Tout traitement lourd tourne dans un QThread (GradeWorker / RenameWorker).
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QProgressBar, QTextEdit,
    QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core import config as cfg_store
from ui.grade_panel import GradePanel
from ui.rename_panel import RenamePanel
from ui.workers import GradeWorker, RenameWorker
from version import FULL_NAME


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker = None
        self._cfg = cfg_store.load()

        self.setWindowTitle(f"{FULL_NAME} — Étalonnage & Renommage")
        self.resize(820, 680)
        self.setMinimumSize(700, 580)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Onglets ─────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.grade_panel  = GradePanel()
        self.rename_panel = RenamePanel()
        self.tabs.addTab(self.grade_panel,  "  Étalonnage  ")
        self.tabs.addTab(self.rename_panel, "  Renommage  ")
        layout.addWidget(self.tabs)

        # ── Boutons d'action ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.run_btn    = QPushButton("▶  Lancer")
        self.cancel_btn = QPushButton("⏹  Annuler")
        self.cancel_btn.setEnabled(False)
        self.run_btn.setFixedHeight(36)
        self.cancel_btn.setFixedHeight(36)
        self.run_btn.clicked.connect(self._on_run)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

        # ── Barre de progression ────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # ── Console ─────────────────────────────────────────────────────────
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 9))
        self.console.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.console)

        # ── Restauration de la config ────────────────────────────────────────
        self.grade_panel.load_config(self._cfg)
        self.rename_panel.load_config(self._cfg)

    def closeEvent(self, event):
        self.grade_panel.save_config(self._cfg)
        self.rename_panel.save_config(self._cfg)
        cfg_store.save(self._cfg)
        super().closeEvent(event)

    # ── Lancement ────────────────────────────────────────────────────────────

    def _on_run(self) -> None:
        if self.tabs.currentIndex() == 0:
            self._start_grading()
        else:
            self._start_renaming()

    def _start_grading(self) -> None:
        params = self.grade_panel.get_params()
        if not params["folder"] or not params["folder"].is_dir():
            QMessageBox.critical(self, "Erreur", "Choisis un dossier source valide.")
            return

        self._log_separator()
        self._log(f"📁 Source  : {params['folder']}")
        self._log(f"   Sortie  : {params['output_dir'] or '_output (par dossier)'}")
        self._log(
            f"   Récursif : {'oui' if params['recursive'] else 'non'}  |  "
            f"Processus : {params['workers']}  |  Suffixe : {params['suffix']}"
        )

        worker = GradeWorker(params)
        worker.log_line.connect(self._log)
        worker.progress.connect(self._update_progress)
        worker.finished.connect(self._on_grade_done)
        self._start_worker(worker)

    def _start_renaming(self) -> None:
        params = self.rename_panel.get_params()
        if not params["base"] or not params["base"].is_dir():
            QMessageBox.critical(self, "Erreur", "Choisis un dossier de base valide.")
            return

        if not params["dry_run"]:
            reply = QMessageBox.question(
                self,
                "Confirmer le renommage",
                "Le renommage modifie les fichiers de façon irréversible.\n\n"
                "Assure-toi d'avoir une sauvegarde.\n\nContinuer ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._log_separator()
        mode = "APERÇU (aucune modification)" if params["dry_run"] else "RENOMMAGE RÉEL"
        self._log(f"📁 Base : {params['base']}")
        self._log(f"   Mode : {mode}\n")

        worker = RenameWorker(params)
        worker.log_line.connect(self._log)
        worker.progress.connect(self._update_progress)
        worker.finished.connect(self._on_rename_done)
        self._start_worker(worker)

    def _start_worker(self, worker) -> None:
        self._worker = worker
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setMaximum(1)
        worker.start()

    # ── Callbacks workers ─────────────────────────────────────────────────────

    def _on_cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._log("\n⏹ Annulation demandée…")

    def _update_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)

    def _on_grade_done(self, result: dict) -> None:
        self._log_separator()
        status = "Annulé" if result.get("cancelled") else "Terminé"
        msg = f"  {status} : {result['ok']} traitée(s), {result['skipped']} ignorée(s)"
        if result["errors"]:
            msg += f", {result['errors']} erreur(s)"
        self._log(msg)
        self._log_separator()
        self._finish()

    def _on_rename_done(self, total_renamed: int, dry_run: bool) -> None:
        self._log_separator()
        verb = "à renommer (aperçu)" if dry_run else "renommée(s)"
        self._log(f"  Terminé : {total_renamed} image(s) {verb}.")
        self._log_separator()
        self._finish()

    def _finish(self) -> None:
        self._worker = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setValue(0)

    # ── Helpers console ────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        self.console.append(text)

    def _log_separator(self) -> None:
        self.console.append("=" * 60)
