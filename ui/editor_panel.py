"""
ui/editor_panel.py — Panneau éditeur v3.0 (presets + corrections manuelles)
===========================================================================
Colonne droite de l'onglet Étalonnage. Style 100 % via ui/style.py (QSS).

Modèle global + surcharge par image :
- « Appliquer à toute la série » coché → les réglages modifient le profil
  GLOBAL (toutes les images sans surcharge).
- décoché → les réglages créent une SURCHARGE pour l'image courante.
"""

from dataclasses import fields

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QSlider, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt, Signal

from core.adjustments import EditParams, PRESETS, DEFAULT_PRESET

# (attribut EditParams, libellé affiché)
SLIDERS = [
    ("exposure",    "Exposition"),
    ("contrast",    "Contraste"),
    ("highlights",  "Hautes lumières"),
    ("shadows",     "Ombres"),
    ("saturation",  "Saturation"),
    ("temperature", "Température"),
    ("sharpness",   "Netteté"),
    ("grain",       "Grain argentique"),
]


class EditorPanel(QWidget):
    changed         = Signal()      # un réglage a changé → recharger l'aperçu
    export_requested = Signal()     # « Télécharger le résultat »

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editor_col")
        self._global = EditParams()
        self._overrides: dict[str, EditParams] = {}
        self._current: str | None = None
        self._loading = False        # garde anti-boucle pendant la maj UI
        self._build()

    # ── Construction ────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # Portée
        self.scope_cb = QCheckBox("Appliquer à toute la série")
        self.scope_cb.setChecked(True)
        self.scope_cb.toggled.connect(self._on_scope_changed)
        root.addWidget(self.scope_cb)

        # ── Presets ───────────────────────────────────────────────────────
        pbox = QFrame()
        pbox.setObjectName("editor_box")
        pv = QVBoxLayout(pbox)
        pv.setContentsMargins(14, 12, 14, 14)
        pv.setSpacing(8)
        title = QLabel("PRESETS AUTOMATIQUES")
        title.setObjectName("editor_title")
        pv.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._preset_btns = {}
        for i, name in enumerate(PRESETS):
            b = QPushButton(name)
            b.setObjectName("preset_btn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=name: self._on_preset(n))
            grid.addWidget(b, i // 2, i % 2)
            self._preset_btns[name] = b
        pv.addLayout(grid)
        root.addWidget(pbox)

        # ── Corrections manuelles ─────────────────────────────────────────
        cbox = QFrame()
        cbox.setObjectName("editor_box")
        cv = QVBoxLayout(cbox)
        cv.setContentsMargins(14, 12, 14, 14)
        cv.setSpacing(6)
        ctitle = QLabel("CORRECTIONS MANUELLES")
        ctitle.setObjectName("editor_title")
        cv.addWidget(ctitle)

        self._sliders = {}
        self._value_lbls = {}
        for attr, label in SLIDERS:
            row_top = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("form_label")
            val = QLabel("0")
            val.setObjectName("slider_value")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_top.addWidget(lbl)
            row_top.addStretch()
            row_top.addWidget(val)
            cv.addLayout(row_top)

            s = QSlider(Qt.Horizontal)
            s.setMinimum(-100)
            s.setMaximum(100)
            s.setValue(0)
            s.valueChanged.connect(lambda v, a=attr: self._on_slider(a, v))
            cv.addWidget(s)
            self._sliders[attr] = s
            self._value_lbls[attr] = val

        root.addWidget(cbox)
        root.addStretch()

        # ── Boutons ────────────────────────────────────────────────────────
        self.btn_export = QPushButton("⬇  Télécharger le résultat")
        self.btn_export.setObjectName("btn_run")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_requested.emit)
        root.addWidget(self.btn_export)

        self.btn_reset = QPushButton("↺  Réinitialiser tous les réglages")
        self.btn_reset.setObjectName("btn_browse")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self._on_reset)
        root.addWidget(self.btn_reset)

        self._sync_ui()

    # ── Cible d'édition (global ou surcharge image) ─────────────────────────

    def _target(self) -> EditParams:
        """EditParams modifié par les contrôles selon la portée."""
        if self.scope_cb.isChecked() or not self._current:
            return self._global
        # surcharge par image : créée depuis le global si absente
        if self._current not in self._overrides:
            self._overrides[self._current] = EditParams.from_dict(self._global.to_dict())
        return self._overrides[self._current]

    def current_edit(self) -> EditParams:
        """Paramètres EFFECTIFS de l'image courante (pour l'aperçu)."""
        if self._current and self._current in self._overrides:
            return self._overrides[self._current]
        return self._global

    def batch_edits(self):
        """(global, {chemin: EditParams}) pour le traitement par lot."""
        return self._global, dict(self._overrides)

    # ── Réactions ────────────────────────────────────────────────────────────

    def _on_preset(self, name: str) -> None:
        if self._loading:
            return
        self._target().preset = name
        self._sync_ui()
        self.changed.emit()

    def _on_slider(self, attr: str, value: int) -> None:
        if self._loading:
            return
        setattr(self._target(), attr, float(value))
        self._value_lbls[attr].setText(str(value))
        self.changed.emit()

    def _on_scope_changed(self, _checked: bool) -> None:
        # bascule l'affichage sur la bonne cible, sans réémettre d'édition
        self._sync_ui()

    def _on_reset(self) -> None:
        tgt = self._target()
        for f in fields(EditParams):
            setattr(tgt, f.name, getattr(EditParams(), f.name))
        if not self.scope_cb.isChecked() and self._current in self._overrides:
            del self._overrides[self._current]   # retour au global
        self._sync_ui()
        self.changed.emit()

    # ── Synchronisation UI ↔ état ───────────────────────────────────────────

    def set_current_image(self, path) -> None:
        self._current = str(path) if path else None
        self._sync_ui()

    def _sync_ui(self) -> None:
        p = self.current_edit() if (not self.scope_cb.isChecked()) else self._global
        self._loading = True
        for name, b in self._preset_btns.items():
            b.setChecked(name == p.preset)
        for attr, s in self._sliders.items():
            v = int(getattr(p, attr))
            s.setValue(v)
            self._value_lbls[attr].setText(str(v))
        self._loading = False

    # ── Config (profil global persistant) ───────────────────────────────────

    def load_config(self, cfg: dict) -> None:
        self._global = EditParams.from_dict(cfg.get("editor_global", {}))
        self.scope_cb.setChecked(cfg.get("editor_scope_series", True))
        self._sync_ui()

    def save_config(self, cfg: dict) -> None:
        cfg["editor_global"] = self._global.to_dict()
        cfg["editor_scope_series"] = self.scope_cb.isChecked()
