"""
core/adjustments.py — Moteur d'édition v3.0 (presets + corrections manuelles)
=============================================================================
Pur NumPy, sans dépendance UI. Deux niveaux :

1. PRESET (look complet, indépendant) :
       Naturel · Cinématique · Noir & Blanc · Vintage · Golden Hour · Froid
   « Naturel » = l'étalonnage adaptatif v3 (blancs neutres, anti-surexpo,
   peau naturelle). Les autres presets sont des looks créatifs autonomes.

2. CORRECTIONS MANUELLES (par-dessus le preset) :
       Exposition · Contraste · Hautes lumières · Ombres · Saturation
       · Température · Netteté · Grain argentique

Règle d'or : preset « Naturel » + tous les curseurs à 0 == sortie v3 identique
au pixel près (le traitement par lot par défaut ne change pas).
"""

from dataclasses import dataclass, asdict, fields

import numpy as np
from PIL import Image, ImageFilter

from core.grading import (
    analyze_image, apply_color_grade, apply_bw_grade, is_grayscale,
)

PRESETS = ["Naturel", "Cinématique", "Noir & Blanc", "Vintage", "Golden Hour", "Froid"]
DEFAULT_PRESET = "Naturel"


# ── Paramètres d'édition ──────────────────────────────────────────────────────

@dataclass
class EditParams:
    """État d'édition : preset + 8 curseurs (chacun dans -100..100, 0 = neutre)."""
    preset:      str   = DEFAULT_PRESET
    exposure:    float = 0.0
    contrast:    float = 0.0
    highlights:  float = 0.0
    shadows:     float = 0.0
    saturation:  float = 0.0
    temperature: float = 0.0
    sharpness:   float = 0.0
    grain:       float = 0.0

    def is_neutral(self) -> bool:
        """True si preset Naturel et tous les curseurs à 0 (= v3 strict)."""
        return self.preset == DEFAULT_PRESET and all(
            getattr(self, f.name) == 0.0 for f in fields(self) if f.name != "preset"
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EditParams":
        if not d:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _luma(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]


def _gaussian(arr: np.ndarray, radius: float) -> np.ndarray:
    img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(img, dtype=np.float32) / 255.0


# ── Corrections manuelles (chacune neutre à 0) ───────────────────────────────

def _exposure(arr, v):           # ±1 EV aux extrêmes
    if v:
        arr *= 2.0 ** (v / 100.0)
    return arr


def _contrast(arr, v):           # pivot 0.5
    if v:
        c = 1.0 + (v / 100.0) * 0.6
        arr -= 0.5; arr *= c; arr += 0.5
    return arr


def _highlights(arr, v):         # +clair / -récupère les hautes lumières
    if v:
        lum = _luma(arr)[:, :, None]
        hmask = np.clip((lum - 0.5) / 0.5, 0, 1)
        arr += (v / 100.0) * 0.5 * hmask * (1 - arr)
    return arr


def _shadows(arr, v):            # +ouvre / -ferme les ombres
    if v:
        lum = _luma(arr)[:, :, None]
        smask = np.clip((0.5 - lum) / 0.5, 0, 1)
        arr += (v / 100.0) * 0.5 * smask * (1 - arr if v > 0 else arr)
    return arr


def _saturation(arr, v):
    if v:
        lum = _luma(arr)[:, :, None]
        s = 1.0 + v / 100.0
        arr[:] = lum + (arr - lum) * s
    return arr


def _temperature(arr, v):        # + = plus chaud, - = plus froid
    if v:
        w = v / 100.0
        arr[:, :, 0] *= 1.0 + 0.15 * w
        arr[:, :, 2] *= 1.0 - 0.15 * w
    return arr


def _sharpness(arr, v):          # masque de netteté (unsharp)
    if v > 0:
        blurred = _gaussian(arr, radius=1.4)
        arr += (v / 100.0) * 0.8 * (arr - blurred)
    return arr


def _grain(arr, v, seed=None):   # grain argentique (bruit de luminance)
    if v > 0:
        rng = np.random.default_rng(seed)
        noise = rng.standard_normal(arr.shape[:2]).astype(np.float32)
        arr += (v / 100.0) * 0.05 * noise[:, :, None]
    return arr


def apply_manual(arr: np.ndarray, p: EditParams, grain_seed=None) -> np.ndarray:
    """Applique les 8 corrections manuelles dans l'ordre, en place."""
    _exposure(arr, p.exposure)
    _contrast(arr, p.contrast)
    _highlights(arr, p.highlights)
    _shadows(arr, p.shadows)
    _temperature(arr, p.temperature)
    _saturation(arr, p.saturation)
    _sharpness(arr, p.sharpness)
    np.clip(arr, 0, 1, out=arr)
    _grain(arr, p.grain, seed=grain_seed)
    np.clip(arr, 0, 1, out=arr)
    return arr


# ── Looks (presets créatifs) ──────────────────────────────────────────────────

def _split_tone(arr, shadow_rgb, hi_rgb, amount):
    """Teinte les ombres et les hautes lumières (color grading cinéma)."""
    lum = _luma(arr)[:, :, None]
    sh = (1.0 - lum)
    hi = lum
    arr += amount * sh * (np.asarray(shadow_rgb, np.float32) - 0.5)
    arr += amount * hi * (np.asarray(hi_rgb, np.float32) - 0.5)
    return arr


def _scurve(arr, strength):
    arr += strength * np.sin(np.pi * arr) * (1 - arr) * arr * 4
    return arr


def look_naturel(arr01: np.ndarray) -> np.ndarray:
    """Étalonnage adaptatif v3 (renvoie un array 0..1)."""
    arr255 = arr01 * 255.0
    if is_grayscale(arr255):
        graded = apply_bw_grade(arr01.copy())
    else:
        m = analyze_image(arr01)
        graded = apply_color_grade(arr01.copy(), m)
    return np.asarray(graded, dtype=np.float32) / 255.0


def look_bw(arr01: np.ndarray) -> np.ndarray:
    """N&B par mixage des canaux (peau éclaircie via le rouge)."""
    gray = 0.40 * arr01[:, :, 0] + 0.46 * arr01[:, :, 1] + 0.14 * arr01[:, :, 2]
    out = np.repeat(gray[:, :, None], 3, axis=2).astype(np.float32)
    _scurve(out, 0.05)
    np.clip(out, 0, 1, out=out)
    return out


def look_cinematique(arr01: np.ndarray) -> np.ndarray:
    out = arr01.copy()
    _scurve(out, 0.04)
    # ombres teal, hautes lumières orange/doré
    _split_tone(out, shadow_rgb=(0.42, 0.52, 0.55), hi_rgb=(0.58, 0.52, 0.43), amount=0.10)
    lum = _luma(out)[:, :, None]                    # légère désaturation
    out[:] = lum + (out - lum) * 0.92
    np.clip(out, 0, 1, out=out)
    return out


def look_vintage(arr01: np.ndarray) -> np.ndarray:
    out = arr01.copy()
    out *= 0.92; out += 0.06                         # noirs délavés
    _split_tone(out, shadow_rgb=(0.52, 0.50, 0.44), hi_rgb=(0.56, 0.52, 0.42), amount=0.08)
    lum = _luma(out)[:, :, None]
    out[:] = lum + (out - lum) * 0.85                # désaturé
    np.clip(out, 0, 1, out=out)
    _grain(out, 35.0, seed=12345)
    np.clip(out, 0, 1, out=out)
    return out


def look_golden(arr01: np.ndarray) -> np.ndarray:
    out = arr01.copy()
    out[:, :, 0] *= 1.08                              # plus chaud
    out[:, :, 2] *= 0.94
    out *= 0.97; out += 0.02                          # lueur douce
    lum = _luma(out)[:, :, None]
    out[:] = lum + (out - lum) * 1.05                 # un peu plus saturé
    np.clip(out, 0, 1, out=out)
    return out


def look_froid(arr01: np.ndarray) -> np.ndarray:
    out = arr01.copy()
    out[:, :, 0] *= 0.95                              # plus froid
    out[:, :, 2] *= 1.08
    _split_tone(out, shadow_rgb=(0.45, 0.50, 0.58), hi_rgb=(0.50, 0.50, 0.52), amount=0.07)
    np.clip(out, 0, 1, out=out)
    return out


_LOOKS = {
    "Naturel":      look_naturel,
    "Cinématique":  look_cinematique,
    "Noir & Blanc": look_bw,
    "Vintage":      look_vintage,
    "Golden Hour":  look_golden,
    "Froid":        look_froid,
}


# ── Rendu unifié ──────────────────────────────────────────────────────────────

def render_with_profile(arr01: np.ndarray, params: EditParams,
                        profile: dict = None, grain_seed=None) -> np.ndarray:
    """Rendu unifié intégrant le profil de série (mode « uniformiser »).

    - preset « Naturel » : base = étalonnage v3, piloté par le profil dossier
      si fourni (rendu uniforme sur la série) ; sinon métriques par image.
    - autres presets : look créatif autonome (le profil ne s'applique pas).
    Puis corrections manuelles par-dessus.
    """
    if params.preset == DEFAULT_PRESET:
        arr255 = arr01 * 255.0
        if is_grayscale(arr255):
            base = np.asarray(apply_bw_grade(arr01.copy()), dtype=np.float32) / 255.0
        else:
            m = profile if profile else analyze_image(arr01)
            base = np.asarray(apply_color_grade(arr01.copy(), m), dtype=np.float32) / 255.0
    else:
        base = _LOOKS.get(params.preset, look_naturel)(arr01)

    if not (params.preset == DEFAULT_PRESET and _all_sliders_zero(params)):
        base = apply_manual(base, params, grain_seed=grain_seed)
    return base


def render(arr01: np.ndarray, params: EditParams, grain_seed=None) -> np.ndarray:
    """Rendu sans profil de série (aperçu simple). Retourne un array 0..1."""
    return render_with_profile(arr01, params, profile=None, grain_seed=grain_seed)


def _all_sliders_zero(p: EditParams) -> bool:
    return all(getattr(p, f.name) == 0.0 for f in fields(p) if f.name != "preset")


def render_to_image(arr01: np.ndarray, params: EditParams, grain_seed=None) -> Image.Image:
    out = render(arr01, params, grain_seed=grain_seed)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
