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
from ui.compare_panel import BeforeAfterView, PreviewWorker, ProfileWorker


class GradePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._images: list[Path] = []
        self._preview_worker = None
        self._preview_token = 0
        self._profile = None              # profil de série (mode uniformiser)
        self._profile_worker = None
        # debounce du chargement quand on déplace le curseur de navigation
        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(130)
        self._nav_timer.timeout.connect(self._load_current_preview)
        self._build()

    def _build(self) -> None:
        # Disposition 2 colonnes : réglages (gauche, compact) | aperçu (droite)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(16)
        root.addWidget(self._build_controls_column())
        root.addWidget(self._build_preview_column(), stretch=1)

    # ── Colonne gauche : réglages compacts ──────────────────────────────────

    def _build_controls_column(self) -> QWidget:
        col = QWidget()
        col.setObjectName("controls_col")
        col.setMinimumWidth(300)
        col.setMaximumWidth(360)
        col.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)

        # ── Dossiers ───────────────────────────────────────────────────────
        folder_box = QGroupBox("DOSSIERS")
        fv = QVBoxLayout(folder_box)
        fv.setContentsMargins(14, 18, 14, 14)
        fv.setSpacing(6)

        self.src_edit = self._path_input("Dossier source…")
        self.out_edit = self._path_input("Vide = _output dans la source")
        self.src_edit.editingFinished.connect(self.refresh_preview)

        for caption, edit in [("Source", self.src_edit), ("Sortie", self.out_edit)]:
            cap = QLabel(caption)
            cap.setObjectName("form_label")
            row = QHBoxLayout()
            row.setSpacing(6)
            browse = QPushButton("…")
            browse.setObjectName("btn_browse")
            browse.setFixedWidth(34)
            browse.setCursor(Qt.PointingHandCursor)
            browse.clicked.connect(lambda _, e=edit: self._browse(e))
            row.addWidget(edit, stretch=1)
            row.addWidget(browse)
            fv.addWidget(cap)
            fv.addLayout(row)

        v.addWidget(folder_box)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("OPTIONS")
        ov = QVBoxLayout(opt_box)
        ov.setContentsMargins(14, 18, 14, 14)
        ov.setSpacing(8)

        _dw = default_workers()
        self.suffix_edit  = QLineEdit(DEFAULT_SUFFIX)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 64)
        self.workers_spin.setValue(_dw)
        self.workers_spin.setToolTip(f"60 % des cœurs physiques détectés ({_dw} par défaut)")
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(DEFAULT_QUALITY)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for row, (text, widget) in enumerate([
            ("Suffixe", self.suffix_edit),
            ("Processus", self.workers_spin),
            ("Qualité", self.quality_spin),
        ]):
            lbl = QLabel(text)
            lbl.setObjectName("form_label")
            grid.addWidget(lbl,    row, 0)
            grid.addWidget(widget, row, 1)
        ov.addLayout(grid)

        self.recursive_cb = QCheckBox("Récursif (sous-dossiers)")
        self.skip_cb      = QCheckBox("Ignorer images déjà traitées")
        self.coherent_cb  = QCheckBox("Uniformiser la série")
        self.coherent_cb.setToolTip(
            "Réglage commun par dossier pour un rendu homogène sur toute la série."
        )
        for cb in (self.recursive_cb, self.skip_cb, self.coherent_cb):
            cb.setChecked(True)
            ov.addWidget(cb)

        self.recursive_cb.toggled.connect(self.refresh_preview)
        self.suffix_edit.editingFinished.connect(self.refresh_preview)
        self.coherent_cb.toggled.connect(self._on_coherent_toggled)

        v.addWidget(opt_box)
        v.addStretch()
        return col

    # ── Colonne droite : aperçu ─────────────────────────────────────────────

    def _build_preview_column(self) -> QWidget:
        prev_box = QGroupBox("APERÇU  AVANT / APRÈS")
        prev_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pv = QVBoxLayout(prev_box)
        pv.setContentsMargins(14, 18, 14, 12)
        pv.setSpacing(8)

        # barre supérieure : recharger + nom fichier + métriques
        top = QHBoxLayout()
        self.preview_btn = QPushButton("Charger l'aperçu")
        self.preview_btn.setObjectName("btn_browse")
        self.preview_btn.setCursor(Qt.PointingHandCursor)
        self.preview_btn.setMinimumWidth(120)
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

        # vue comparateur (curseur central = avant/après)
        self.view = BeforeAfterView()
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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

        hint = QLabel("Curseur central : comparer avant/après · "
                      "curseur du bas / flèches : changer d'image.")
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        pv.addWidget(hint)

        self._set_nav_enabled(False)
        return prev_box

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
            self._recompute_profile()      # (ré)calcule le profil si « uniformiser »
            self._load_current_preview()

    # ── Profil de série (mode uniformiser) ──────────────────────────────────

    def _on_coherent_toggled(self, _checked: bool) -> None:
        self._recompute_profile()
        self._load_current_preview()

    def _recompute_profile(self) -> None:
        """Calcule (hors UI) le profil moyen du dossier si « uniformiser » coché."""
        if not (self.coherent_cb.isChecked() and self._images):
            self._profile = None
            return
        self.preview_info.setText("Calcul du profil de série…")
        worker = ProfileWorker(list(self._images))
        worker.done.connect(self._on_profile_done)
        self._profile_worker = worker
        worker.start()

    def _on_profile_done(self, profile) -> None:
        self._profile = profile
        self._load_current_preview()       # recharge avec le profil appliqué

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
        # profil de série appliqué si « uniformiser » est coché
        prof = self._profile if self.coherent_cb.isChecked() else None
        worker = PreviewWorker(path, profile=prof)
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
