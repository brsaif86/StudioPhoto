"""
ui/grade_panel.py — Onglet Étalonnage v2
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QSpinBox, QLabel,
    QFileDialog, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt

from core.grading import DEFAULT_SUFFIX, DEFAULT_QUALITY, default_workers


class GradePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(16)

        # ── Dossiers ──────────────────────────────────────────────────────
        folder_box = QGroupBox("DOSSIERS")
        fl = QGridLayout(folder_box)
        fl.setContentsMargins(16, 20, 16, 16)
        fl.setSpacing(10)
        fl.setColumnStretch(1, 1)

        self.src_edit = self._path_input("Chemin du dossier source…")
        self.out_edit = self._path_input("Vide = sous-dossier _output dans la source")

        for row, (text, edit) in enumerate([
            ("Source :", self.src_edit),
            ("Sortie :", self.out_edit),
        ]):
            lbl = QLabel(text)
            lbl.setObjectName("form_label")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            browse = QPushButton("Parcourir…")
            browse.setObjectName("btn_browse")
            browse.setCursor(Qt.PointingHandCursor)
            browse.clicked.connect(lambda _, e=edit: self._browse(e))
            fl.addWidget(lbl,   row, 0)
            fl.addWidget(edit,  row, 1)
            fl.addWidget(browse, row, 2)

        root.addWidget(folder_box)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("OPTIONS")
        ol = QGridLayout(opt_box)
        ol.setContentsMargins(16, 20, 16, 16)
        ol.setSpacing(12)
        ol.setColumnStretch(1, 1)
        ol.setColumnStretch(3, 1)

        # Colonne gauche : paramètres numériques
        _dw = default_workers()

        self.suffix_edit  = QLineEdit(DEFAULT_SUFFIX)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(_dw)
        self.workers_spin.setToolTip(f"60 % des cœurs physiques détectés ({_dw} par défaut)")
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(DEFAULT_QUALITY)

        for row, (text, widget) in enumerate([
            ("Suffixe :",      self.suffix_edit),
            ("Processus :",    self.workers_spin),
            ("Qualité JPEG :", self.quality_spin),
        ]):
            lbl = QLabel(text)
            lbl.setObjectName("form_label")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ol.addWidget(lbl,    row, 0)
            ol.addWidget(widget, row, 1)

        # Colonne droite : cases à cocher
        self.recursive_cb = QCheckBox("Récursif (sous-dossiers)")
        self.skip_cb      = QCheckBox("Ignorer les images déjà traitées (reprise)")
        self.coherent_cb  = QCheckBox("Uniformiser la série (profil moyen/dossier)")
        self.coherent_cb.setToolTip(
            "Calcule un réglage commun par dossier pour un rendu homogène\n"
            "sur toute la série (corrige les variations d'exposition/couleur)."
        )
        self.recursive_cb.setChecked(True)
        self.skip_cb.setChecked(True)
        self.coherent_cb.setChecked(True)   # activé par défaut

        ol.addWidget(self.recursive_cb, 0, 3)
        ol.addWidget(self.skip_cb,      1, 3)
        ol.addWidget(self.coherent_cb,  2, 3)

        root.addWidget(opt_box)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _path_input(placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        return e

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)

    # ── Config ──────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        src = self.src_edit.text().strip()
        out = self.out_edit.text().strip()
        return {
            "folder":     Path(src).resolve() if src else None,
            "output_dir": Path(out).resolve() if out else None,
            "suffix":     self.suffix_edit.text().strip() or DEFAULT_SUFFIX,
            "recursive":  self.recursive_cb.isChecked(),
            "skip":       self.skip_cb.isChecked(),
            "workers":    self.workers_spin.value(),
            "quality":    self.quality_spin.value(),
            "coherent":   self.coherent_cb.isChecked(),
        }

    def load_config(self, cfg: dict) -> None:
        self.src_edit.setText(cfg.get("grade_source", ""))
        self.out_edit.setText(cfg.get("grade_output", ""))
        self.suffix_edit.setText(cfg.get("grade_suffix", DEFAULT_SUFFIX))
        self.recursive_cb.setChecked(cfg.get("grade_recursive", True))
        self.skip_cb.setChecked(cfg.get("grade_skip", True))
        self.coherent_cb.setChecked(cfg.get("grade_coherent", True))
        self.workers_spin.setValue(cfg.get("grade_workers", default_workers()))
        self.quality_spin.setValue(cfg.get("grade_quality", DEFAULT_QUALITY))

    def save_config(self, cfg: dict) -> None:
        cfg["grade_source"]    = self.src_edit.text().strip()
        cfg["grade_output"]    = self.out_edit.text().strip()
        cfg["grade_suffix"]    = self.suffix_edit.text().strip()
        cfg["grade_recursive"] = self.recursive_cb.isChecked()
        cfg["grade_skip"]      = self.skip_cb.isChecked()
        cfg["grade_coherent"]  = self.coherent_cb.isChecked()
        cfg["grade_workers"]   = self.workers_spin.value()
        cfg["grade_quality"]   = self.quality_spin.value()
