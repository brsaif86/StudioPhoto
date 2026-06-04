"""
ui/rename_panel.py — Onglet Renommage v2
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel,
    QFileDialog, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt


class RenamePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(16)

        # ── Dossier ────────────────────────────────────────────────────────
        folder_box = QGroupBox("DOSSIER DE BASE")
        fl = QGridLayout(folder_box)
        fl.setContentsMargins(16, 20, 16, 16)
        fl.setSpacing(10)
        fl.setColumnStretch(1, 1)

        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("Dossier contenant les sous-dossiers à renommer…")
        lbl = QLabel("Base :")
        lbl.setObjectName("form_label")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        browse = QPushButton("Parcourir…")
        browse.setObjectName("btn_browse")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(lambda: self._browse(self.base_edit))

        fl.addWidget(lbl,            0, 0)
        fl.addWidget(self.base_edit, 0, 1)
        fl.addWidget(browse,         0, 2)

        root.addWidget(folder_box)

        # ── Description ────────────────────────────────────────────────────
        info = QLabel(
            "Chaque sous-dossier est renommé d'après son propre nom :\n"
            "Mariage/  →  Mariage_001.jpg · Mariage_002.jpg · …\n\n"
            "La numérotation reprend là où elle s'est arrêtée.\n"
            "Les trous de séquence sont détectés et signalés."
        )
        info.setObjectName("hint_label")
        info.setWordWrap(True)
        root.addWidget(info)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("OPTIONS")
        ol = QVBoxLayout(opt_box)
        ol.setContentsMargins(16, 20, 16, 16)
        ol.setSpacing(10)

        self.include_root_cb = QCheckBox("Inclure aussi le dossier de base lui-même")
        self.dryrun_cb = QCheckBox("Aperçu seulement — aucun fichier modifié")
        self.dryrun_cb.setChecked(True)

        ol.addWidget(self.include_root_cb)
        ol.addWidget(self.dryrun_cb)

        root.addWidget(opt_box)
        root.addStretch()

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)

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
