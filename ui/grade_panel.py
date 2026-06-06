"""
ui/grade_panel.py — Onglet Étalonnage v3 (avec aperçu avant/après intégré)
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QCheckBox, QSpinBox, QLabel,
    QFileDialog, QGroupBox, QSizePolicy, QComboBox, QSlider,
)
from PySide6.QtCore import Qt, QTimer

from core.grading import (
    DEFAULT_SUFFIX, DEFAULT_QUALITY, default_workers, list_source_images,
)
from ui.compare_panel import BeforeAfterView, PreviewWorker, ProfileWorker, ExportWorker
from ui.editor_panel import EditorPanel


class GradePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._images: list[Path] = []
        self._nav_idx = 0                 # index image courante dans l'aperçu
        self._preview_token = 0
        self._profile = None              # profil de série (mode uniformiser)
        # QThreads vivants : référence forte tant qu'ils tournent, sinon le GC
        # détruit le QThread en cours d'exécution → crash de l'application.
        self._workers: list = []
        # debounce du chargement quand on déplace le curseur de navigation
        self._nav_timer = QTimer(self)
        self._nav_timer.setSingleShot(True)
        self._nav_timer.setInterval(130)
        self._nav_timer.timeout.connect(self._load_current_preview)
        self._build()

    def _build(self) -> None:
        # 2 colonnes : aperçu (centre, extensible) | éditeur (droite)
        # Les réglages (Dossiers/Options) vivent dans le footer (bas de fenêtre).
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(14)
        root.addWidget(self._build_preview_column(), stretch=6)   # aperçu 60 %

        self.editor = EditorPanel()
        self.editor.setMinimumWidth(260)                          # éditeur 40 %
        self.editor.changed.connect(self._load_current_preview)
        self.editor.export_requested.connect(self._export_current)
        self.editor.pipette_toggled.connect(self.view.set_pick_mode)
        self.view.picked.connect(self.editor.set_white_balance)
        root.addWidget(self.editor, stretch=4)                    # éditeur 40 %

        self._footer = self._build_footer()      # placé par l'app en bas

    def footer(self) -> QWidget:
        return self._footer

    # ── Footer compact : Dossiers + Options (côte à côte) ────────────────────

    def _build_footer(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        # ── Dossiers ───────────────────────────────────────────────────────
        folder_box = QGroupBox("DOSSIERS")
        fg = QGridLayout(folder_box)
        fg.setContentsMargins(12, 16, 12, 10)
        fg.setHorizontalSpacing(6)
        fg.setVerticalSpacing(6)
        fg.setColumnStretch(1, 1)

        self.src_edit = self._path_input("Dossier source…")
        self.out_edit = self._path_input("Vide = _output dans la source")
        self.src_edit.editingFinished.connect(self.refresh_preview)
        for r, (cap, edit) in enumerate([("Source", self.src_edit), ("Sortie", self.out_edit)]):
            lbl = QLabel(cap); lbl.setObjectName("form_label")
            browse = QPushButton("…"); browse.setObjectName("btn_browse")
            browse.setFixedWidth(30); browse.setCursor(Qt.PointingHandCursor)
            browse.clicked.connect(lambda _, e=edit: self._browse(e))
            fg.addWidget(lbl, r, 0); fg.addWidget(edit, r, 1); fg.addWidget(browse, r, 2)
        h.addWidget(folder_box, stretch=1)

        # ── Options ────────────────────────────────────────────────────────
        opt_box = QGroupBox("OPTIONS")
        og = QGridLayout(opt_box)
        og.setContentsMargins(12, 16, 12, 10)
        og.setHorizontalSpacing(10)
        og.setVerticalSpacing(6)

        _dw = default_workers()
        self.suffix_edit  = QLineEdit(DEFAULT_SUFFIX)
        self.suffix_edit.setMaximumWidth(110)
        self.workers_spin = QSpinBox(); self.workers_spin.setRange(1, 64); self.workers_spin.setValue(_dw)
        self.workers_spin.setMaximumWidth(70)
        self.quality_spin = QSpinBox(); self.quality_spin.setRange(60, 100); self.quality_spin.setValue(DEFAULT_QUALITY)
        self.quality_spin.setMaximumWidth(70)
        # ligne 1 : Suffixe | Processus | Qualité
        for col, (text, widget) in enumerate([
            ("Suffixe", self.suffix_edit), ("Processus", self.workers_spin), ("Qualité", self.quality_spin),
        ]):
            lbl = QLabel(text); lbl.setObjectName("form_label")
            og.addWidget(lbl, 0, col * 2)
            og.addWidget(widget, 0, col * 2 + 1)

        self.recursive_cb = QCheckBox("Récursif")
        self.skip_cb      = QCheckBox("Ignorer déjà traitées")
        self.coherent_cb  = QCheckBox("Uniformiser la série")
        for cb in (self.recursive_cb, self.skip_cb, self.coherent_cb):
            cb.setChecked(True)
        og.addWidget(self.recursive_cb, 1, 0, 1, 2)
        og.addWidget(self.skip_cb,      1, 2, 1, 2)
        og.addWidget(self.coherent_cb,  1, 4, 1, 2)

        self.recursive_cb.toggled.connect(self.refresh_preview)
        self.suffix_edit.editingFinished.connect(self.refresh_preview)
        self.coherent_cb.toggled.connect(self._on_coherent_toggled)

        h.addWidget(opt_box, stretch=1)

        # ── Rendu & LUT ─────────────────────────────────────────────────────
        lut_box = QGroupBox("RENDU & LUT")
        lg = QGridLayout(lut_box)
        lg.setContentsMargins(12, 16, 12, 10)
        lg.setHorizontalSpacing(10)
        lg.setVerticalSpacing(6)

        self.lut_dir_edit = QLineEdit()
        self.lut_dir_edit.setReadOnly(True)
        self.lut_dir_edit.setPlaceholderText("Dossier LUTs")
        self.lut_dir_edit.setMaximumWidth(180)

        self.btn_lut_dir = QPushButton("📂")
        self.btn_lut_dir.setObjectName("btn_browse")
        self.btn_lut_dir.setFixedWidth(30)
        self.btn_lut_dir.setCursor(Qt.PointingHandCursor)
        self.btn_lut_dir.clicked.connect(self._browse_lut_dir)

        self.lut_combo = QComboBox()
        self.lut_combo.setFixedWidth(150)
        self.lut_combo.currentTextChanged.connect(self._on_lut_changed)

        self.strength_slider = QSlider(Qt.Horizontal)
        self.strength_slider.setRange(0, 100)
        self.strength_slider.setValue(85)
        self.strength_slider.setFixedWidth(120)
        self.strength_slider.valueChanged.connect(self._on_lut_changed)

        self.vibrance_slider = QSlider(Qt.Horizontal)
        self.vibrance_slider.setRange(-50, 50)
        self.vibrance_slider.setValue(10)
        self.vibrance_slider.setFixedWidth(120)
        self.vibrance_slider.valueChanged.connect(self._on_lut_changed)

        self.lut_count_lbl = QLabel("0 LUTs")
        self.lut_count_lbl.setObjectName("hint_label")

        # Layout
        lg.addWidget(QLabel("Dossier"), 0, 0)
        lg.addWidget(self.lut_dir_edit, 0, 1)
        lg.addWidget(self.btn_lut_dir, 0, 2)
        lg.addWidget(self.lut_count_lbl, 0, 3)

        lg.addWidget(QLabel("LUT"), 1, 0)
        lg.addWidget(self.lut_combo, 1, 1)
        lg.addWidget(QLabel("Intensité"), 1, 2)
        lg.addWidget(self.strength_slider, 1, 3)

        lg.addWidget(QLabel("Vibrance"), 2, 0)
        lg.addWidget(self.vibrance_slider, 2, 1)

        h.addWidget(lut_box, stretch=1)
        return w

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

        # navigation entre les images du dossier (boutons Précédent / Suivant)
        nav = QHBoxLayout()
        nav.setSpacing(12)
        self.prev_arrow = QPushButton("‹  Précédent")
        self.next_arrow = QPushButton("Suivant  ›")
        for b in (self.prev_arrow, self.next_arrow):
            b.setObjectName("btn_browse")
            b.setMinimumWidth(120)
            b.setCursor(Qt.PointingHandCursor)
        self.prev_arrow.clicked.connect(lambda: self._step(-1))
        self.next_arrow.clicked.connect(lambda: self._step(1))

        self.nav_index = QLabel("0 / 0")
        self.nav_index.setObjectName("progress_file")
        self.nav_index.setMinimumWidth(120)
        self.nav_index.setAlignment(Qt.AlignCenter)

        nav.addStretch()
        nav.addWidget(self.prev_arrow)
        nav.addWidget(self.nav_index)
        nav.addWidget(self.next_arrow)
        nav.addStretch()
        pv.addLayout(nav)

        hint = QLabel("Curseur central : comparer avant/après · "
                      "Précédent / Suivant : changer d'image.")
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
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

    def _browse_lut_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier LUTs")
        if path:
            self.lut_dir_edit.setText(path)
            self._update_lut_list()
            self._on_lut_changed()

    def _update_lut_list(self) -> None:
        path = self.lut_dir_edit.text().strip()
        if not path:
            self.lut_combo.clear()
            self.lut_combo.addItem("Aucune")
            self.lut_count_lbl.setText("0 LUTs")
            return

        from core.lut_engine import LutEngine
        engine = LutEngine(path)
        luts = engine.list_luts()
        self.lut_combo.clear()
        self.lut_combo.addItem("Aucune")
        self.lut_combo.addItems(luts)
        self.lut_count_lbl.setText(f"{len(luts)} LUTs")

    def _on_lut_changed(self) -> None:
        self._load_current_preview()

    def _set_nav_enabled(self, on: bool) -> None:
        self.prev_arrow.setEnabled(on)
        self.next_arrow.setEnabled(on)

    def _update_arrows(self) -> None:
        n = len(self._images)
        self.prev_arrow.setEnabled(self._nav_idx > 0)
        self.next_arrow.setEnabled(self._nav_idx < n - 1)

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
        self._nav_idx = 0
        if n == 0:
            self.view.clear()
            self.preview_name.setText("Aucune image dans ce dossier")
            self.preview_info.setText("")
            self.nav_index.setText("0 / 0")
            self._set_nav_enabled(False)
        else:
            self.nav_index.setText(f"1 / {n}")
            self.preview_name.setText(self._images[0].name)
            self._update_arrows()
            self._recompute_profile()      # (ré)calcule le profil si « uniformiser »
            self._load_current_preview()

    # ── Profil de série (mode uniformiser) ──────────────────────────────────

    def _track(self, worker) -> None:
        """Démarre un QThread en gardant une référence forte jusqu'à sa fin."""
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._untrack(w))
        worker.start()

    def _untrack(self, worker) -> None:
        try:
            self._workers.remove(worker)
        except ValueError:
            pass

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
        self._track(worker)

    def _on_profile_done(self, profile) -> None:
        self._profile = profile
        self._load_current_preview()       # recharge avec le profil appliqué

    def _step(self, delta: int) -> None:
        n = len(self._images)
        if not n:
            return
        new = max(0, min(n - 1, self._nav_idx + delta))
        if new == self._nav_idx:
            return
        self._nav_idx = new
        self.nav_index.setText(f"{new + 1} / {n}")
        self.preview_name.setText(self._images[new].name)
        self.preview_info.setText("Étalonnage…")
        self._update_arrows()
        self._nav_timer.start()          # débounce : coalesce les clics rapides

    def _load_current_preview(self) -> None:
        if not self._images:
            return
        idx = self._nav_idx
        if idx < 0 or idx >= len(self._images):
            return
        path = self._images[idx]
        self.editor.set_current_image(path)
        self._preview_token += 1
        token = self._preview_token
        # profil de série appliqué si « uniformiser » est coché
        prof = self._profile if self.coherent_cb.isChecked() else None
        worker = PreviewWorker(
            path,
            profile=prof,
            edit=self.editor.current_edit(),
            lut_dir=self.lut_dir_edit.text().strip(),
            lut_name=self.lut_combo.currentText() if self.lut_combo.currentIndex() > 0 else None,
            lut_strength=self.strength_slider.value() / 100.0,
            vibrance=self.vibrance_slider.value() / 100.0
        )
        worker.done.connect(
            lambda o, g, m, met, t=token: self._on_preview_done(o, g, m, met, t)
        )
        worker.error.connect(lambda msg, t=token: self._on_preview_error(msg, t))
        self._track(worker)

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

    # ── Export d'une image ──────────────────────────────────────────────────

    def _export_current(self) -> None:
        if not self._images:
            return
        path = self._images[self._nav_idx]
        default = path.stem + "_graded.jpg"
        out, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le résultat", default, "Image JPEG (*.jpg *.jpeg)"
        )
        if not out:
            return
        prof = self._profile if self.coherent_cb.isChecked() else None
        self.preview_info.setText("Enregistrement…")
        worker = ExportWorker(
            str(path), out, prof, self.editor.current_edit(),
            self.quality_spin.value(),
            lut_dir=self.lut_dir_edit.text().strip(),
            lut_name=self.lut_combo.currentText() if self.lut_combo.currentIndex() > 0 else None,
            lut_strength=self.strength_slider.value() / 100.0,
            vibrance=self.vibrance_slider.value() / 100.0
        )
        worker.done.connect(self._on_export_done)
        self._track(worker)

    def _on_export_done(self, ok: bool, msg: str) -> None:
        self.preview_info.setText("✓ Enregistré" if ok else f"Échec : {msg}")

    # ── Config ──────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        src = self.src_edit.text().strip()
        out = self.out_edit.text().strip()
        edit_global, edits_by_path = self.editor.batch_edits()
        return {
            "folder":        Path(src).resolve() if src else None,
            "output_dir":    Path(out).resolve() if out else None,
            "suffix":        self.suffix_edit.text().strip() or DEFAULT_SUFFIX,
            "recursive":     self.recursive_cb.isChecked(),
            "skip":          self.skip_cb.isChecked(),
            "workers":       self.workers_spin.value(),
            "quality":       self.quality_spin.value(),
            "coherent":      self.coherent_cb.isChecked(),
            "edit_global":   edit_global,
            "edits_by_path": edits_by_path,
            "lut_dir":       self.lut_dir_edit.text().strip(),
            "lut_name":      self.lut_combo.currentText() if self.lut_combo.currentIndex() > 0 else None,
            "lut_strength":  self.strength_slider.value() / 100.0,
            "vibrance":      self.vibrance_slider.value() / 100.0,
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

        self.lut_dir_edit.setText(cfg.get("lut_dir", "assets/luts"))
        self._update_lut_list()

        lut_name = cfg.get("lut_name")
        if lut_name:
            idx = self.lut_combo.findText(lut_name)
            if idx != -1:
                self.lut_combo.setCurrentIndex(idx)

        self.strength_slider.setValue(int(cfg.get("lut_strength", 0.85) * 100))
        self.vibrance_slider.setValue(int(cfg.get("vibrance", 0.10) * 100))

        self.editor.load_config(cfg)
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

        cfg["lut_dir"]       = self.lut_dir_edit.text().strip()
        cfg["lut_name"]       = self.lut_combo.currentText() if self.lut_combo.currentIndex() > 0 else None
        cfg["lut_strength"]   = self.strength_slider.value() / 100.0
        cfg["vibrance"]       = self.vibrance_slider.value() / 100.0

        self.editor.save_config(cfg)
