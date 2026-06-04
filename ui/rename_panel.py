"""
ui/rename_panel.py — Onglet Renommage
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel,
    QFileDialog, QGroupBox,
)
from PySide6.QtCore import Qt


class RenamePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 8)

        # ── Dossier ────────────────────────────────────────────────────────
        folder_box = QGroupBox("Dossier de base")
        fl = QFormLayout(folder_box)
        fl.setLabelAlignment(Qt.AlignRight)

        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("Dossier contenant les sous-dossiers à renommer…")
        base_row = self._browse_row(self.base_edit)
        fl.addRow("Base :", base_row)

        root.addWidget(folder_box)

        # ── Description ────────────────────────────────────────────────────
        info = QLabel(
            "Chaque sous-dossier est renommé d'après son propre nom :\n"
            "  Mariage/ → Mariage_001.jpg, Mariage_002.jpg, …\n\n"
            "La numérotation reprend là où elle s'est arrêtée (reprise).\n"
            "Les trous éventuels dans la séquence sont signalés."
        )
        info.setStyleSheet("color: #666; font-size: 12px;")
        root.addWidget(info)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("Options")
        ol = QVBoxLayout(opt_box)

        self.include_root_cb = QCheckBox("Inclure aussi le dossier de base lui-même")
        self.dryrun_cb = QCheckBox("Aperçu seulement — aucun fichier modifié")
        self.dryrun_cb.setChecked(True)
        ol.addWidget(self.include_root_cb)
        ol.addWidget(self.dryrun_cb)

        root.addWidget(opt_box)
        root.addStretch()

    def _browse_row(self, edit: QLineEdit) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit)
        btn = QPushButton("Parcourir…")
        btn.setFixedWidth(100)
        btn.clicked.connect(lambda: self._browse(edit))
        h.addWidget(btn)
        return row

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)

    # ── Lecture / écriture des valeurs ─────────────────────────────────────

    def get_params(self) -> dict:
        base = self.base_edit.text().strip()
        return {
            "base":         Path(base).resolve() if base else None,
            "include_root": self.include_root_cb.isChecked(),
            "dry_run":      self.dryrun_cb.isChecked(),
        }

    def load_config(self, cfg: dict) -> None:
        self.base_edit.setText(cfg.get("rename_base", ""))
        self.include_root_cb.setChecked(cfg.get("rename_include_root", False))
        self.dryrun_cb.setChecked(cfg.get("rename_dryrun", True))

    def save_config(self, cfg: dict) -> None:
        cfg["rename_base"]         = self.base_edit.text().strip()
        cfg["rename_include_root"] = self.include_root_cb.isChecked()
        cfg["rename_dryrun"]       = self.dryrun_cb.isChecked()
