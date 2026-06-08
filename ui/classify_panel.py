"""
ui/classify_panel.py — Onglet Classification (few-shot / zero-shot SigLIP)
=========================================================================
Style uniquement via ui/style.py (objectName + QSS). Aucun setStyleSheet inline.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel, QComboBox,
    QFileDialog, QGroupBox, QSpinBox, QDoubleSpinBox,
)
from PySide6.QtCore import Qt, Signal

from core.classification import DEFAULT_THRESHOLD, LABELS, assets_available


class ClassifyPanel(QWidget):
    train_requested = Signal(str)        # dossier(s) d'apprentissage trié(s)

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

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Manifest (results.json) — non destructif", "manifest")
        self.mode_combo.addItem("Copier dans des sous-dossiers", "copy")
        self.mode_combo.addItem("Déplacer dans des sous-dossiers", "move")

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setSingleStep(0.05)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(DEFAULT_THRESHOLD)
        self.threshold_spin.setToolTip(
            "Sous ce seuil, l'image va dans « À revoir » au lieu d'être forcée.")

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 64)
        self.batch_spin.setValue(16)

        # Moteur : Few-shot (apprend tes tris) ou zero-shot SigLIP
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Few-shot — apprend tes tris (recommandé)", "fewshot")
        self.engine_combo.addItem("Zero-shot SigLIP — sans entraînement", "clip")
        self.engine_combo.setToolTip(
            "Few-shot : apprend de tes dossiers déjà triés (le plus fiable, "
            "rapide, 100 % local) — à entraîner ci-dessous.\n"
            "Zero-shot : SigLIP via des descriptions texte, sans entraînement "
            "(plus limité sur les catégories subjectives).")

        for row, (lbl_txt, widget) in enumerate([
            ("Sortie :",  self.mode_combo),
            ("Seuil :",   self.threshold_spin),
            ("Lot :",     self.batch_spin),
            ("Moteur :",  self.engine_combo),
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
        og.addWidget(cats, 1, 3, 3, 1)
        root.addWidget(box_opt)

        # ── Apprentissage few-shot ────────────────────────────────────────────
        box_fs = QGroupBox("APPRENTISSAGE (FEW-SHOT)")
        fg = QGridLayout(box_fs)
        fg.setColumnStretch(1, 1)

        self.train_edit = self._path_input(
            "Dossiers d'exemples triés (sous-dossiers = catégories) — "
            "« Ajouter » pour cumuler plusieurs mariages…")
        self.train_edit.setToolTip(
            "Un ou plusieurs mariages déjà triés, séparés par « ; ». Les noms sont "
            "normalisés (« 01 Preparations » = « Preparations ») et les dossiers de "
            "sélection (highlights, best…) sont ignorés automatiquement.")
        lbl_tr = QLabel("Exemples :")
        lbl_tr.setObjectName("form_label")
        lbl_tr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        btn_tr = QPushButton("Ajouter…")
        btn_tr.setObjectName("btn_browse")
        btn_tr.setFixedWidth(90)
        btn_tr.setCursor(Qt.PointingHandCursor)
        btn_tr.clicked.connect(self._add_train_folder)
        self.btn_train = QPushButton("Entraîner")
        self.btn_train.setObjectName("btn_browse")
        self.btn_train.setFixedWidth(90)
        self.btn_train.setCursor(Qt.PointingHandCursor)
        self.btn_train.clicked.connect(self._on_train_clicked)
        fg.addWidget(lbl_tr, 0, 0)
        fg.addWidget(self.train_edit, 0, 1)
        fg.addWidget(btn_tr, 0, 2)
        fg.addWidget(self.btn_train, 0, 3)

        self.model_status = QLabel("")
        self.model_status.setObjectName("hint_label")
        self.model_status.setWordWrap(True)
        fg.addWidget(self.model_status, 1, 1, 1, 3)
        root.addWidget(box_fs)

        # ── Aide ──────────────────────────────────────────────────────────────
        hint = QLabel(
            "Few-shot : entraîne une fois sur des mariages déjà triés, puis le tri "
            "est quasi instantané (~ms/photo), 100 % local."
            + ("" if assets_available()
               else "  ⚠ Modèle SigLIP absent : génère ses assets avec "
                    "tools/export_clip_assets.py.")
        )
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch()

        self.refresh_model_info()

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

    # ── Apprentissage few-shot ────────────────────────────────────────────────

    def _add_train_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Ajouter un mariage trié")
        if not path:
            return
        parts = [p.strip() for p in self.train_edit.text().split(";") if p.strip()]
        if path not in parts:
            parts.append(path)
        self.train_edit.setText(" ; ".join(parts))

    def _on_train_clicked(self) -> None:
        dirs = [d.strip() for d in self.train_edit.text().split(";") if d.strip()]
        valid = [d for d in dirs if Path(d).is_dir()]
        if not valid:
            self.model_status.setText("⚠ Indique au moins un dossier d'exemples "
                                      "valide (sous-dossiers = catégories).")
            return
        self.btn_train.setEnabled(False)
        self.train_requested.emit(" ; ".join(valid))

    def refresh_model_info(self) -> None:
        """Met à jour l'état du modèle few-shot (et réactive « Entraîner »)."""
        self.btn_train.setEnabled(True)
        try:
            from core.fewshot import model_info
            info = model_info()
        except Exception:
            info = None
        if not info:
            self.model_status.setText(
                "Aucun modèle few-shot entraîné. Indique un ou plusieurs dossiers "
                "déjà triés (un sous-dossier par catégorie) puis « Entraîner ».")
            return
        acc = info.get("acc", float("nan"))
        acc_txt = f" · préc. {acc:.0%}" if acc == acc else ""
        self.model_status.setText(
            f"✓ Modèle few-shot : {len(info['labels'])} catégories "
            f"({', '.join(info['labels'])}) · {info['n']} exemples{acc_txt}")

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
            "engine":     self.engine_combo.currentData(),
        }

    def load_config(self, cfg: dict) -> None:
        self.src_edit.setText(cfg.get("classify_source", ""))
        self.out_edit.setText(cfg.get("classify_output", ""))
        idx = self.mode_combo.findData(cfg.get("classify_mode", "manifest"))
        self.mode_combo.setCurrentIndex(max(0, idx))
        self.threshold_spin.setValue(cfg.get("classify_threshold", DEFAULT_THRESHOLD))
        self.batch_spin.setValue(cfg.get("classify_batch", 16))
        self.recursive_cb.setChecked(cfg.get("classify_recursive", True))
        self.train_edit.setText(cfg.get("classify_train_dir", ""))
        eidx = self.engine_combo.findData(cfg.get("classify_engine", "fewshot"))
        self.engine_combo.setCurrentIndex(max(0, eidx))

    def save_config(self, cfg: dict) -> None:
        cfg["classify_source"]    = self.src_edit.text().strip()
        cfg["classify_output"]    = self.out_edit.text().strip()
        cfg["classify_mode"]      = self.mode_combo.currentData()
        cfg["classify_threshold"] = self.threshold_spin.value()
        cfg["classify_batch"]     = self.batch_spin.value()
        cfg["classify_recursive"] = self.recursive_cb.isChecked()
        cfg["classify_train_dir"] = self.train_edit.text().strip()
        cfg["classify_engine"]    = self.engine_combo.currentData()
