"""
ui/grade_panel.py — Onglet Étalonnage v3 (avec aperçu avant/après intégré)
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QSpinBox, QLabel,
    QFileDialog, QGroupBox, QSizePolicy, QSlider,
)
from PySide6.QtCore import Qt, QTimer

from core.grading import (
    DEFAULT_SUFFIX, DEFAULT_QUALITY, default_workers, list_source_images,
)
from ui.compare_panel import BeforeAfterView, PreviewWorker


class GradePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._images: list[Path] = []
        self._preview_worker = None
        self._preview_token = 0
        # debounce du chargement quand on déplace le curseur de navigation
        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(130)
        self._nav_timer.timeout.connect(self._load_current_preview)
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
        self.src_edit.editingFinished.connect(self.refresh_preview)

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
            fl.addWidget(lbl,    row, 0)
            fl.addWidget(edit,   row, 1)
            fl.addWidget(browse, row, 2)

        root.addWidget(folder_box)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("OPTIONS")
        ol = QGridLayout(opt_box)
        ol.setContentsMargins(16, 20, 16, 16)
        ol.setSpacing(12)
        ol.setColumnStretch(1, 1)
        ol.setColumnStretch(3, 1)

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

        self.recursive_cb = QCheckBox("Récursif (sous-dossiers)")
        self.skip_cb      = QCheckBox("Ignorer les images déjà traitées (reprise)")
        self.coherent_cb  = QCheckBox("Uniformiser la série (profil moyen/dossier)")
        self.coherent_cb.setToolTip(
            "Calcule un réglage commun par dossier pour un rendu homogène\n"
            "sur toute la série (corrige les variations d'exposition/couleur)."
        )
        self.recursive_cb.setChecked(True)
        self.skip_cb.setChecked(True)
        self.coherent_cb.setChecked(True)
        self.recursive_cb.toggled.connect(self.refresh_preview)
        self.suffix_edit.editingFinished.connect(self.refresh_preview)

        ol.addWidget(self.recursive_cb, 0, 3)
        ol.addWidget(self.skip_cb,      1, 3)
        ol.addWidget(self.coherent_cb,  2, 3)

        root.addWidget(opt_box)

        # ── Aperçu avant / après ────────────────────────────────────────────
        prev_box = QGroupBox("APERÇU  AVANT / APRÈS")
        pv = QVBoxLayout(prev_box)
        pv.setContentsMargins(16, 20, 16, 14)
        pv.setSpacing(10)

        # barre supérieure : bouton recharger + nom fichier + métriques
        top = QHBoxLayout()
        self.preview_btn = QPushButton("Charger l'aperçu")
        self.preview_btn.setObjectName("btn_browse")
        self.preview_btn.setCursor(Qt.PointingHandCursor)
        self.preview_btn.setMinimumWidth(130)
        self.preview_btn.clicked.connect(self.refresh_preview)
        self.preview_name = QLabel("—")
        self.preview_name.setObjectName("progress_file")
        self.preview_info = QLabel("")
        self.preview_info.setObjectName("hint_label")
        top.addWidget(self.preview_btn)
        top.addSpacing(12)
        top.addWidget(self.preview_name)
        top.addStretch()
        top.addWidget(self.preview_info)
        pv.addLayout(top)

        # vue comparateur (glisser le curseur central = comparer avant/après)
        self.view = BeforeAfterView()
        pv.addWidget(self.view, stretch=1)

        # navigation entre les images du dossier
        nav = QHBoxLayout()
        self.prev_arrow = QPushButton("‹")
        self.next_arrow = QPushButton("›")
        for b in (self.prev_arrow, self.next_arrow):
            b.setObjectName("btn_browse")
            b.setFixedWidth(40)
            b.setCursor(Qt.PointingHandCursor)
        self.prev_arrow.clicked.connect(lambda: self._step(-1))
        self.next_arrow.clicked.connect(lambda: self._step(1))

        self.nav_slider = QSlider(Qt.Horizontal)
        self.nav_slider.setMinimum(0)
        self.nav_slider.setMaximum(0)
        self.nav_slider.valueChanged.connect(self._on_nav_changed)

        self.nav_index = QLabel("0 / 0")
        self.nav_index.setObjectName("hint_label")
        self.nav_index.setMinimumWidth(70)
        self.nav_index.setAlignment(Qt.AlignCenter)

        nav.addWidget(self.prev_arrow)
        nav.addWidget(self.nav_slider, stretch=1)
        nav.addWidget(self.next_arrow)
        nav.addWidget(self.nav_index)
        pv.addLayout(nav)

        hint = QLabel("Glisse le curseur central pour comparer avant/après · "
                      "le curseur du bas (ou les flèches) passe d'une image à l'autre.")
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        pv.addWidget(hint)

        self._set_nav_enabled(False)
        root.addWidget(prev_box, stretch=1)

    # ── Helpers UI ──────────────────────────────────────────────────────────

    @staticmethod
    def _path_input(placeholder: str) -> QLineEdit:
        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        return e

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if path:
            edit.setText(path)
            if edit is self.src_edit:
                self.refresh_preview()

    def _set_nav_enabled(self, on: bool) -> None:
        for w in (self.nav_slider, self.prev_arrow, self.next_arrow):
            w.setEnabled(on)

    # ── Aperçu : scan + navigation ──────────────────────────────────────────

    def refresh_preview(self) -> None:
        """(Re)liste les images du dossier source et charge la première."""
        src = self.src_edit.text().strip()
        folder = Path(src) if src else None
        if not folder or not folder.is_dir():
            self._images = []
            self.view.clear()
            self.preview_name.setText("—")
            self.preview_info.setText("")
            self.nav_index.setText("0 / 0")
            self._set_nav_enabled(False)
            return

        suffix = self.suffix_edit.text().strip() or DEFAULT_SUFFIX
        self._images = list_source_images(folder, suffix, self.recursive_cb.isChecked())
        n = len(self._images)
        self.nav_slider.blockSignals(True)
        self.nav_slider.setMaximum(max(0, n - 1))
        self.nav_slider.setValue(0)
        self.nav_slider.blockSignals(False)
        self._set_nav_enabled(n > 0)
        if n == 0:
            self.view.clear()
            self.preview_name.setText("Aucune image dans ce dossier")
            self.preview_info.setText("")
            self.nav_index.setText("0 / 0")
        else:
            self.nav_index.setText(f"1 / {n}")
            self.preview_name.setText(self._images[0].name)
            self._load_current_preview()

    def _step(self, delta: int) -> None:
        self.nav_slider.setValue(
            max(0, min(self.nav_slider.maximum(), self.nav_slider.value() + delta))
        )

    def _on_nav_changed(self, value: int) -> None:
        n = len(self._images)
        if n:
            self.nav_index.setText(f"{value + 1} / {n}")
            self.preview_name.setText(self._images[value].name)
            self.preview_info.setText("Étalonnage…")
        self._nav_timer.start()          # débounce : charge après l'arrêt du curseur

    def _load_current_preview(self) -> None:
        if not self._images:
            return
        idx = self.nav_slider.value()
        if idx < 0 or idx >= len(self._images):
            return
        path = self._images[idx]
        self._preview_token += 1
        token = self._preview_token
        worker = PreviewWorker(path)
        worker.done.connect(
            lambda o, g, m, met, t=token: self._on_preview_done(o, g, m, met, t)
        )
        worker.error.connect(lambda msg, t=token: self._on_preview_error(msg, t))
        self._preview_worker = worker
        worker.start()

    def _on_preview_done(self, orig_px, graded_px, mode, metrics, token) -> None:
        if token != self._preview_token:
            return                       # résultat périmé (curseur a bougé depuis)
        self.view.set_images(orig_px, graded_px)
        if metrics:
            lum = metrics.get("mean_lum", 0)
            lum_label = "sombre" if lum < 0.45 else "moyenne" if lum < 0.60 else "lumineuse"
            self.preview_info.setText(
                f"{mode}  ·  lum: {lum_label}  ·  "
                f"cast: {metrics.get('warm_cast', 0):+.2f}  ·  "
                f"hl: {metrics.get('highlight_ratio', 0):.0%}"
            )
        else:
            self.preview_info.setText(f"{mode}")

    def _on_preview_error(self, msg, token) -> None:
        if token != self._preview_token:
            return
        self.view.clear()
        self.preview_info.setText(f"Erreur : {msg}")

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
        # Charge l'aperçu si un dossier valide est mémorisé
        if self.src_edit.text().strip():
            QTimer.singleShot(0, self.refresh_preview)

    def save_config(self, cfg: dict) -> None:
        cfg["grade_source"]    = self.src_edit.text().strip()
        cfg["grade_output"]    = self.out_edit.text().strip()
        cfg["grade_suffix"]    = self.suffix_edit.text().strip()
        cfg["grade_recursive"] = self.recursive_cb.isChecked()
        cfg["grade_skip"]      = self.skip_cb.isChecked()
        cfg["grade_coherent"]  = self.coherent_cb.isChecked()
        cfg["grade_workers"]   = self.workers_spin.value()
        cfg["grade_quality"]   = self.quality_spin.value()
