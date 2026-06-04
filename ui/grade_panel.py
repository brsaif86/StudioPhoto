"""
ui/grade_panel.py — Onglet Étalonnage
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QSpinBox, QLabel,
    QFileDialog, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

from core.grading import DEFAULT_SUFFIX, DEFAULT_QUALITY, default_workers


class GradePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)

        # ── Dossiers ──────────────────────────────────────────────────────
        folder_box = QGroupBox("Dossiers")
        fl = QFormLayout(folder_box)
        fl.setLabelAlignment(Qt.AlignRight)

        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Dossier source des photos JPEG…")
        src_row = self._browse_row(self.src_edit)
        fl.addRow("Source :", src_row)

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Vide = sous-dossier _output dans la source")
        out_row = self._browse_row(self.out_edit)
        fl.addRow("Sortie :", out_row)

        root.addWidget(folder_box)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("Options")
        ol = QHBoxLayout(opt_box)

        # gauche : suffixe + workers + qualité
        left = QFormLayout()
        left.setLabelAlignment(Qt.AlignRight)

        self.suffix_edit = QLineEdit(DEFAULT_SUFFIX)
        self.suffix_edit.setMaximumWidth(100)
        left.addRow("Suffixe :", self.suffix_edit)

        _dw = default_workers()
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(_dw)
        self.workers_spin.setMaximumWidth(70)
        self.workers_spin.setToolTip(
            f"60 % des cœurs physiques détectés ({_dw} par défaut sur cette machine)"
        )
        left.addRow("Processus :", self.workers_spin)

        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(DEFAULT_QUALITY)
        self.quality_spin.setMaximumWidth(70)
        left.addRow("Qualité JPEG :", self.quality_spin)

        ol.addLayout(left)
        ol.addSpacing(32)

        # droite : cases à cocher
        right = QVBoxLayout()
        self.recursive_cb = QCheckBox("Récursif (inclure les sous-dossiers)")
        self.recursive_cb.setChecked(True)
        self.skip_cb = QCheckBox("Ignorer les images déjà traitées (reprise)")
        self.skip_cb.setChecked(True)
        right.addWidget(self.recursive_cb)
        right.addWidget(self.skip_cb)
        right.addStretch()
        ol.addLayout(right)

        root.addWidget(opt_box)
        root.addStretch()

    def _browse_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit)
        btn = QPushButton("Parcourir…")
        btn.setObjectName("btn_browse")
        btn.setFixedWidth(90)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self._browse(edit))
        h.addWidget(btn)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)

    # ── Lecture / écriture des valeurs ─────────────────────────────────────

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
        }

    def load_config(self, cfg: dict) -> None:
        self.src_edit.setText(cfg.get("grade_source", ""))
        self.out_edit.setText(cfg.get("grade_output", ""))
        self.suffix_edit.setText(cfg.get("grade_suffix", DEFAULT_SUFFIX))
        self.recursive_cb.setChecked(cfg.get("grade_recursive", True))
        self.skip_cb.setChecked(cfg.get("grade_skip", True))
        self.workers_spin.setValue(cfg.get("grade_workers", default_workers()))
        self.quality_spin.setValue(cfg.get("grade_quality", DEFAULT_QUALITY))

    def save_config(self, cfg: dict) -> None:
        cfg["grade_source"]    = self.src_edit.text().strip()
        cfg["grade_output"]    = self.out_edit.text().strip()
        cfg["grade_suffix"]    = self.suffix_edit.text().strip()
        cfg["grade_recursive"] = self.recursive_cb.isChecked()
        cfg["grade_skip"]      = self.skip_cb.isChecked()
        cfg["grade_workers"]   = self.workers_spin.value()
        cfg["grade_quality"]   = self.quality_spin.value()
