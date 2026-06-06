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
    QPushButton, QSlider, QCheckBox, QFrame, QScrollArea,
    QComboBox, QInputDialog,
)
from PySide6.QtCore import Qt, Signal

from core.adjustments import EditParams, PRESETS, DEFAULT_PRESET, BASE_PRESETS, LOOK_PRESETS

# (attribut EditParams, libellé affiché)
SLIDERS = [
    ("exposure",    "Exposition"),
    ("contrast",    "Contraste"),
    ("highlights",  "Hautes lumières"),
    ("shadows",     "Ombres"),
    ("temperature", "Température"),
    ("tint",        "Teinte"),
    ("vibrance",    "Vibrance"),
    ("saturation",  "Saturation"),
    ("clarity",     "Clarté"),
    ("sharpness",   "Netteté"),
    ("vignette",    "Vignettage"),
    ("grain",       "Grain argentique"),
]


class EditorPanel(QWidget):
    changed          = Signal()     # un réglage a changé → recharger l'aperçu
    export_requested = Signal()     # « Enregistrer les modifications »
    pipette_toggled  = Signal(bool) # active/désactive la pipette BdB sur l'aperçu

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editor_col")
        self._global = EditParams()
        self._overrides: dict[str, EditParams] = {}
        self._current: str | None = None
        self._loading = False        # garde anti-boucle pendant la maj UI
        self._custom: dict[str, dict] = {}   # presets utilisateur : nom -> dict
        self._build()

    # ── Construction ────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Portée
        self.scope_cb = QCheckBox("Appliquer à toute la série")
        self.scope_cb.setChecked(True)
        self.scope_cb.toggled.connect(self._on_scope_changed)
        root.addWidget(self.scope_cb)

        # Zone défilante (12 curseurs + presets)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)

        # ── Presets automatiques ──────────────────────────────────────────
        pbox = QFrame(); pbox.setObjectName("editor_box")
        pv = QVBoxLayout(pbox); pv.setContentsMargins(14, 12, 14, 14); pv.setSpacing(8)
        t1 = QLabel("PRESETS AUTOMATIQUES"); t1.setObjectName("editor_title")
        pv.addWidget(t1)
        grid = QGridLayout(); grid.setSpacing(8)
        self._preset_btns = {}
        for i, name in enumerate(PRESETS):
            b = QPushButton(name)
            b.setObjectName("preset_btn"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=name: self._on_preset(n))
            grid.addWidget(b, i // 2, i % 2)
            self._preset_btns[name] = b
        pv.addLayout(grid)
        col.addWidget(pbox)

        # ── Mes presets (personnalisés) ───────────────────────────────────
        mbox = QFrame(); mbox.setObjectName("editor_box")
        mv = QVBoxLayout(mbox); mv.setContentsMargins(14, 12, 14, 14); mv.setSpacing(8)
        t2 = QLabel("MES PRESETS"); t2.setObjectName("editor_title")
        mv.addWidget(t2)
        row = QHBoxLayout(); row.setSpacing(6)
        self.custom_combo = QComboBox()
        self.custom_combo.setMinimumWidth(120)
        self.btn_apply_custom = QPushButton("Appliquer")
        self.btn_apply_custom.setObjectName("btn_browse")
        self.btn_apply_custom.setCursor(Qt.PointingHandCursor)
        self.btn_apply_custom.clicked.connect(self._apply_custom)
        self.btn_del_custom = QPushButton("✕")
        self.btn_del_custom.setObjectName("btn_browse")
        self.btn_del_custom.setFixedWidth(32)
        self.btn_del_custom.setCursor(Qt.PointingHandCursor)
        self.btn_del_custom.clicked.connect(self._delete_custom)
        row.addWidget(self.custom_combo, 1)
        row.addWidget(self.btn_apply_custom)
        row.addWidget(self.btn_del_custom)
        mv.addLayout(row)
        self.btn_save_custom = QPushButton("＋  Enregistrer le réglage actuel")
        self.btn_save_custom.setObjectName("btn_browse")
        self.btn_save_custom.setCursor(Qt.PointingHandCursor)
        self.btn_save_custom.clicked.connect(self._save_custom)
        mv.addWidget(self.btn_save_custom)
        col.addWidget(mbox)

        # ── Corrections manuelles ─────────────────────────────────────────
        cbox = QFrame(); cbox.setObjectName("editor_box")
        cv = QVBoxLayout(cbox); cv.setContentsMargins(14, 12, 14, 14); cv.setSpacing(6)
        chead = QHBoxLayout()
        t3 = QLabel("CORRECTIONS MANUELLES"); t3.setObjectName("editor_title")
        self.btn_pipette = QPushButton("⛏ Pipette BdB")
        self.btn_pipette.setObjectName("btn_browse")
        self.btn_pipette.setCheckable(True)
        self.btn_pipette.setCursor(Qt.PointingHandCursor)
        self.btn_pipette.setToolTip("Clique sur une zone neutre/grise de l'aperçu "
                                    "pour corriger la balance des blancs.")
        self.btn_pipette.toggled.connect(self.pipette_toggled.emit)
        chead.addWidget(t3); chead.addStretch(); chead.addWidget(self.btn_pipette)
        cv.addLayout(chead)

        self._sliders = {}
        self._value_lbls = {}
        for attr, label in SLIDERS:
            rt = QHBoxLayout()
            lbl = QLabel(label); lbl.setObjectName("form_label")
            val = QLabel("0"); val.setObjectName("slider_value")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rt.addWidget(lbl); rt.addStretch(); rt.addWidget(val)
            cv.addLayout(rt)
            s = QSlider(Qt.Horizontal)
            s.setMinimum(-100); s.setMaximum(100); s.setValue(0)
            s.valueChanged.connect(lambda v, a=attr: self._on_slider(a, v))
            cv.addWidget(s)
            self._sliders[attr] = s
            self._value_lbls[attr] = val
        col.addWidget(cbox)
        col.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        # ── Boutons fixes (hors défilement) ────────────────────────────────
        self.btn_export = QPushButton("💾  Enregistrer les modifications")
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
        tgt = self._target()
        presets = list(tgt.presets)
        if name in BASE_PRESETS:
            # base exclusive : remplace l'ancienne base, garde les looks
            presets = [name] + [p for p in presets if p in LOOK_PRESETS]
        else:
            # look additif : on/off
            if name in presets:
                presets.remove(name)
            else:
                presets.append(name)
            if not any(b in presets for b in BASE_PRESETS):
                presets.insert(0, DEFAULT_PRESET)   # toujours une base
        tgt.presets = presets
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

    # ── Presets personnalisés ────────────────────────────────────────────────

    def _save_custom(self) -> None:
        name, ok = QInputDialog.getText(self, "Mon preset", "Nom du preset :")
        name = name.strip()
        if not (ok and name):
            return
        self._custom[name] = self._target().to_dict()
        self._refresh_custom_combo(select=name)

    def _apply_custom(self) -> None:
        name = self.custom_combo.currentText()
        if name not in self._custom:
            return
        src = EditParams.from_dict(self._custom[name])
        tgt = self._target()
        for f in fields(EditParams):
            setattr(tgt, f.name, getattr(src, f.name))
        tgt.presets = list(src.presets)
        self._sync_ui()
        self.changed.emit()

    def _delete_custom(self) -> None:
        name = self.custom_combo.currentText()
        if name in self._custom:
            del self._custom[name]
            self._refresh_custom_combo()

    def _refresh_custom_combo(self, select: str = None) -> None:
        self.custom_combo.blockSignals(True)
        self.custom_combo.clear()
        self.custom_combo.addItems(sorted(self._custom.keys()))
        if select:
            i = self.custom_combo.findText(select)
            if i >= 0:
                self.custom_combo.setCurrentIndex(i)
        self.custom_combo.blockSignals(False)
        has = bool(self._custom)
        self.btn_apply_custom.setEnabled(has)
        self.btn_del_custom.setEnabled(has)

    # ── Pipette balance des blancs ───────────────────────────────────────────

    def set_white_balance(self, r: float, g: float, b: float) -> None:
        """Calcule température + teinte pour neutraliser la couleur cliquée."""
        r, g, b = max(r, 1e-3), max(g, 1e-3), max(b, 1e-3)
        w = (b - r) / (0.15 * (r + b))                 # échelle -1..1
        temp = max(-100.0, min(100.0, w * 100.0))
        m = (r * (1 + 0.15 * w) + b * (1 - 0.15 * w)) / 2.0
        t = (1.0 - m / g) / 0.12
        tint = max(-100.0, min(100.0, t * 100.0))
        tgt = self._target()
        tgt.temperature = float(round(temp))
        tgt.tint = float(round(tint))
        self.btn_pipette.setChecked(False)
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
            b.setChecked(name in p.presets)
        for attr, s in self._sliders.items():
            v = int(getattr(p, attr))
            s.setValue(v)
            self._value_lbls[attr].setText(str(v))
        self._loading = False

    # ── Config (profil global persistant) ───────────────────────────────────

    def load_config(self, cfg: dict) -> None:
        self._global = EditParams.from_dict(cfg.get("editor_global", {}))
        self.scope_cb.setChecked(cfg.get("editor_scope_series", True))
        self._custom = dict(cfg.get("editor_custom_presets", {}))
        self._refresh_custom_combo()
        self._sync_ui()

    def save_config(self, cfg: dict) -> None:
        cfg["editor_global"] = self._global.to_dict()
        cfg["editor_scope_series"] = self.scope_cb.isChecked()
        cfg["editor_custom_presets"] = dict(self._custom)
