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
from PySide6.QtCore import Qt, QTimer, Signal

from core.classification import DEFAULT_THRESHOLD, LABELS, assets_available
from ui.workers import OllamaDetectWorker


class ClassifyPanel(QWidget):
    train_requested = Signal(str)        # (dossier d'apprentissage trié)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ollama_url = "http://localhost:11434"
        self._ollama_timeout = 300
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

        # Moteur d'analyse : Hybride (reco) · Ollama local · CLIP intégré
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Few-shot — apprend tes tris (fiable + rapide)", "fewshot")
        self.engine_combo.addItem("Hybride — CLIP + Ollama si incertain", "hybrid")
        self.engine_combo.addItem("Ollama local — analyse visuelle (qualité)", "ollama")
        self.engine_combo.addItem("CLIP — zero-shot intégré, rapide", "clip")
        self.engine_combo.setToolTip(
            "Few-shot : apprend de tes dossiers déjà triés (le plus fiable, rapide, "
            "100 % local) — à entraîner ci-dessous.\n"
            "Hybride : CLIP classe tout, et seules les photos incertaines passent à "
            "un modèle vision Ollama local.\n"
            "Ollama : analyse visuelle locale pour tout (plus lent, ~secondes/photo).\n"
            "CLIP : zero-shot embarqué, rapide mais limité sur catégories subjectives.")

        # Modèle vision Ollama : liste déroulante des modèles détectés (éditable)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItem("(auto — 1er modèle vision)", "")
        self.model_combo.setToolTip(
            "Modèle vision local. La liste se remplit avec les modèles Ollama "
            "détectés ; tu peux aussi saisir un nom manuellement.")
        self.btn_detect = QPushButton("Détecter")
        self.btn_detect.setObjectName("btn_browse")
        self.btn_detect.setFixedWidth(80)
        self.btn_detect.setCursor(Qt.PointingHandCursor)
        self.btn_detect.clicked.connect(lambda: self._detect_models(verbose=True))
        model_row = QWidget()
        mrl = QHBoxLayout(model_row)
        mrl.setContentsMargins(0, 0, 0, 0)
        mrl.setSpacing(6)
        mrl.addWidget(self.model_combo, 1)
        mrl.addWidget(self.btn_detect)

        # Seuil hybride : sous cette confiance CLIP, on demande au LLM
        self.hybrid_spin = QDoubleSpinBox()
        self.hybrid_spin.setRange(0.0, 1.0)
        self.hybrid_spin.setSingleStep(0.05)
        self.hybrid_spin.setDecimals(2)
        self.hybrid_spin.setValue(0.55)
        self.hybrid_spin.setToolTip(
            "Mode hybride : si la confiance de CLIP est sous ce seuil, la photo "
            "est repassée au modèle Ollama. Plus haut = plus de photos au LLM "
            "(plus lent, plus fin).")

        for row, (lbl_txt, widget) in enumerate([
            ("Sortie :",       self.mode_combo),
            ("Seuil :",        self.threshold_spin),
            ("Lot :",          self.batch_spin),
            ("Moteur :",       self.engine_combo),
            ("Modèle :",       model_row),
            ("Seuil hybride :", self.hybrid_spin),
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

        # État de détection Ollama (rempli par le worker)
        self.ollama_status = QLabel("")
        self.ollama_status.setObjectName("hint_label")
        self.ollama_status.setWordWrap(True)
        og.addWidget(self.ollama_status, 3, 3, 2, 1)

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

        # active/désactive modèle + seuil hybride selon le moteur
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        self._on_engine_changed()
        self.refresh_model_info()

        # ── Aide moteur ───────────────────────────────────────────────────────
        hint = QLabel(
            "Hybride/Ollama : 100 % local (Ollama doit être lancé). Le LLM vision "
            "est plus lent (~secondes/photo) mais meilleur sur les catégories "
            "subjectives ; CLIP reste instantané. Repli auto si Ollama est absent."
            + ("" if assets_available()
               else "  ⚠ CLIP non installé : génère ses assets avec "
                    "tools/export_clip_assets.py.")
        )
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addStretch()

        self._detect_worker = None
        # détection auto au démarrage (différée pour ne pas retarder l'affichage)
        QTimer.singleShot(300, lambda: self._detect_models(verbose=False))

    def _on_engine_changed(self, *_) -> None:
        eng = self.engine_combo.currentData()
        uses_ollama = eng in ("ollama", "hybrid")
        self.model_combo.setEnabled(uses_ollama)
        self.btn_detect.setEnabled(uses_ollama)
        self.hybrid_spin.setEnabled(eng == "hybrid")

    # ── Détection des modèles vision Ollama (hors thread UI) ──────────────────

    def _detect_models(self, verbose: bool = False) -> None:
        if self._detect_worker is not None:      # détection déjà en cours
            return
        if verbose:
            self.ollama_status.setText("Détection d'Ollama en cours…")
        self.btn_detect.setEnabled(False)
        w = OllamaDetectWorker(self._ollama_url, parent=self)
        w.done.connect(self._on_models_detected)
        w.finished.connect(self._clear_detect_worker)
        self._detect_worker = w
        w.start()

    def _clear_detect_worker(self) -> None:
        self._detect_worker = None
        self._on_engine_changed()                # restaure l'état des boutons

    def _on_models_detected(self, up: bool, models: list) -> None:
        current = self.model_combo.currentData() or self.model_combo.currentText().strip()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("(auto — 1er modèle vision)", "")
        for m in models:
            self.model_combo.addItem(m, m)
        # restaure la sélection précédente si toujours présente
        idx = self.model_combo.findData(current) if current else 0
        self.model_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.model_combo.blockSignals(False)

        if not up:
            self.ollama_status.setText("⚠ Ollama non détecté (serveur éteint). "
                                       "L'hybride utilisera CLIP seul.")
        elif not models:
            self.ollama_status.setText("⚠ Ollama lancé mais aucun modèle vision "
                                       "installé (ex. ollama pull qwen2.5vl).")
        else:
            self.ollama_status.setText(f"✓ Ollama : {len(models)} modèle(s) vision "
                                       f"détecté(s) — {', '.join(models)}")

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
        cur = self.train_edit.text().strip()
        parts = [p.strip() for p in cur.split(";") if p.strip()]
        if path not in parts:
            parts.append(path)
        self.train_edit.setText(" ; ".join(parts))

    def _on_train_clicked(self) -> None:
        raw = self.train_edit.text().strip()
        dirs = [d.strip() for d in raw.split(";") if d.strip()]
        valid = [d for d in dirs if Path(d).is_dir()]
        if not valid:
            self.model_status.setText("⚠ Indique au moins un dossier d'exemples "
                                      "valide (sous-dossiers = catégories).")
            return
        self.btn_train.setEnabled(False)
        self.train_requested.emit(" ; ".join(valid))

    def refresh_model_info(self) -> None:
        """Met à jour l'étiquette d'état du modèle few-shot (et réactive Entraîner)."""
        self.btn_train.setEnabled(True)
        try:
            from core.fewshot import model_info
            info = model_info()
        except Exception:
            info = None
        if not info:
            self.model_status.setText(
                "Aucun modèle few-shot entraîné. Indique un dossier d'exemples "
                "déjà triés (un sous-dossier par catégorie) puis « Entraîner ».")
            return
        acc = info.get("acc", float("nan"))
        acc_txt = f" · préc. {acc:.0%}" if acc == acc else ""
        self.model_status.setText(
            f"✓ Modèle few-shot : {len(info['labels'])} catégories "
            f"({', '.join(info['labels'])}) · {info['n']} exemples{acc_txt}")

    def _selected_model(self):
        """Nom du modèle choisi, ou None pour « auto »."""
        data = self.model_combo.currentData()
        if data:                                   # vrai modèle sélectionné
            return data
        txt = self.model_combo.currentText().strip()
        if not txt or txt.startswith("("):         # libellé « (auto …) »
            return None
        return txt                                 # nom saisi manuellement

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
            "engine":           self.engine_combo.currentData(),
            "ollama_model":     self._selected_model(),
            "ollama_url":       self._ollama_url,
            "ollama_timeout":   self._ollama_timeout,
            "hybrid_threshold": self.hybrid_spin.value(),
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
        m = (cfg.get("ollama_model", "") or "").strip()
        if m:
            if self.model_combo.findData(m) < 0:
                self.model_combo.addItem(m, m)
            self.model_combo.setCurrentIndex(self.model_combo.findData(m))
        else:
            self.model_combo.setCurrentIndex(0)
        self.hybrid_spin.setValue(cfg.get("classify_hybrid_threshold", 0.55))
        self._ollama_url     = cfg.get("ollama_url", "http://localhost:11434")
        self._ollama_timeout = cfg.get("ollama_timeout", 300)
        self._on_engine_changed()

    def save_config(self, cfg: dict) -> None:
        cfg["classify_source"]    = self.src_edit.text().strip()
        cfg["classify_output"]    = self.out_edit.text().strip()
        cfg["classify_mode"]      = self.mode_combo.currentData()
        cfg["classify_threshold"] = self.threshold_spin.value()
        cfg["classify_batch"]     = self.batch_spin.value()
        cfg["classify_recursive"] = self.recursive_cb.isChecked()
        cfg["classify_train_dir"] = self.train_edit.text().strip()
        cfg["classify_engine"]    = self.engine_combo.currentData()
        cfg["classify_hybrid_threshold"] = self.hybrid_spin.value()
        cfg["ollama_model"]       = self._selected_model() or ""
        cfg["ollama_url"]         = getattr(self, "_ollama_url", "http://localhost:11434")
        cfg["ollama_timeout"]     = getattr(self, "_ollama_timeout", 300)
