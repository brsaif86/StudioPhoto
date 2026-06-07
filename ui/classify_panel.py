"""
ui/classify_panel.py — Onglet Classification (tri auto zero-shot)
=================================================================
Style uniquement via ui/style.py (objectName + QSS). Aucun setStyleSheet inline.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel, QComboBox,
    QFileDialog, QGroupBox, QSpinBox, QDoubleSpinBox,
)
from PySide6.QtCore import Qt

from core.classification import DEFAULT_THRESHOLD, LABELS, assets_available


class ClassifyPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # ── Dossiers ──────────────────────────────────────────────────────────
        box_dir = QGroupBox("DOSSIERS")
        g = QGridLayout(box_dir)
        g.setColumnStretch(1, 1)

        self.src_edit = self._path_input("Dossier source des photos à trier…")
        self.out_edit = self._path_input("Vide = à côté de la source")
        for row, (lbl_txt, edit) in enumerate([
            ("Source :", self.src_edit), ("Sortie :", self.out_edit)
        ]):
            lbl = QLabel(lbl_txt)
            lbl.setObjectName("form_label")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            btn = QPushButton("Parcourir…")
            btn.setObjectName("btn_browse")
            btn.setFixedWidth(90)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, e=edit: self._browse(e))
            g.addWidget(lbl, row, 0)
            g.addWidget(edit, row, 1)
            g.addWidget(btn, row, 2)
        root.addWidget(box_dir)

        # ── Options ───────────────────────────────────────────────────────────
        box_opt = QGroupBox("OPTIONS")
        og = QGridLayout(box_opt)
        og.setColumnStretch(1, 1)
        og.setColumnStretch(3, 1)

        # Mode de sortie
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Manifest (results.json) — non destructif", "manifest")
        self.mode_combo.addItem("Copier dans des sous-dossiers", "copy")
        self.mode_combo.addItem("Déplacer dans des sous-dossiers", "move")

        # Seuil de confiance
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(DEFAULT_THRESHOLD)
        self.threshold_spin.setToolTip(
            "Sous ce seuil, l'image va dans « À revoir » au lieu d'être forcée."
        )

        # Taille de lot
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 64)
        self.batch_spin.setValue(16)

        for row, (lbl_txt, widget) in enumerate([
            ("Sortie :",  self.mode_combo),
            ("Seuil :",   self.threshold_spin),
            ("Lot :",     self.batch_spin),
        ]):
            lbl = QLabel(lbl_txt)
            lbl.setObjectName("form_label")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            og.addWidget(lbl, row, 0)
            og.addWidget(widget, row, 1)

        self.recursive_cb = QCheckBox("Récursif (sous-dossiers)")
        self.recursive_cb.setChecked(True)
        og.addWidget(self.recursive_cb, 0, 3)

        cats = QLabel("Catégories : " + " · ".join(LABELS) + " · À revoir")
        cats.setObjectName("hint_label")
        cats.setWordWrap(True)
        og.addWidget(cats, 1, 3, 2, 1)

        root.addWidget(box_opt)

        # ── Avertissement modèle absent ───────────────────────────────────────
        if not assets_available():
            warn = QLabel(
                "⚠ Modèle de classification absent. Place mobileclip_image.onnx, "
                "text_embeddings.npy et clip_meta.json dans le dossier assets/ "
                "(génère-les avec tools/export_clip_assets.py)."
            )
            warn.setObjectName("hint_label")
            warn.setWordWrap(True)
            root.addWidget(warn)

        root.addStretch()

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _path_input(placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        return e

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)

    # ── Config ──────────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        src = self.src_edit.text().strip()
        out = self.out_edit.text().strip()
        return {
            "folder":     Path(src).resolve() if src else None,
            "output_dir": Path(out).resolve() if out else None,
            "mode":       self.mode_combo.currentData(),
            "threshold":  self.threshold_spin.value(),
            "recursive":  self.recursive_cb.isChecked(),
            "batch_size": self.batch_spin.value(),
        }

    def load_config(self, cfg: dict) -> None:
        self.src_edit.setText(cfg.get("classify_source", ""))
        self.out_edit.setText(cfg.get("classify_output", ""))
        idx = self.mode_combo.findData(cfg.get("classify_mode", "manifest"))
        self.mode_combo.setCurrentIndex(max(0, idx))
        self.threshold_spin.setValue(cfg.get("classify_threshold", DEFAULT_THRESHOLD))
        self.batch_spin.setValue(cfg.get("classify_batch", 16))
        self.recursive_cb.setChecked(cfg.get("classify_recursive", True))

    def save_config(self, cfg: dict) -> None:
        cfg["classify_source"]    = self.src_edit.text().strip()
        cfg["classify_output"]    = self.out_edit.text().strip()
        cfg["classify_mode"]      = self.mode_combo.currentData()
        cfg["classify_threshold"] = self.threshold_spin.value()
        cfg["classify_batch"]     = self.batch_spin.value()
        cfg["classify_recursive"] = self.recursive_cb.isChecked()
