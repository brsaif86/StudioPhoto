"""
core/adjustments.py — Moteur d'édition v3.0 (presets + corrections manuelles)
=============================================================================
Pur NumPy, sans dépendance UI. Deux niveaux :

1. PRESET (look complet, indépendant) :
       Naturel · Noir & Blanc · Cinématique
   « Naturel » = l'étalonnage adaptatif v3 (blancs neutres, anti-surexpo,
   peau naturelle, série cohérente) : il répond à lui seul à TOUTES les
   exigences client validées. « Cinématique » ajoute une touche ciné
   par-dessus. « Noir & Blanc » = conversion N&B.

2. CORRECTIONS MANUELLES (par-dessus le preset) :
       Exposition · Contraste · Hautes lumières · Ombres · Saturation
       · Température · Netteté · Grain argentique

Règle d'or : preset « Naturel » + tous les curseurs à 0 == sortie v3 identique
au pixel près (le traitement par lot par défaut ne change pas).
"""

from dataclasses import dataclass, asdict, field, fields

import numpy as np
from PIL import Image, ImageFilter

from core.grading import (
    analyze_image, apply_color_grade, apply_bw_grade, is_grayscale,
)

DEFAULT_PRESET = "Naturel"
BASE_PRESETS = ["Naturel", "Noir & Blanc"]    # bases exclusives (correction)
LOOK_PRESETS = ["Cinématique"]                # touche créative empilable
PRESETS = ["Naturel", "Noir & Blanc", "Cinématique"]

_SLIDER_NAMES = ("exposure", "contrast", "highlights", "shadows",
                 "temperature", "tint", "vibrance", "saturation",
                 "clarity", "sharpness", "vignette", "grain")


# ── Paramètres d'édition ──────────────────────────────────────────────────────

@dataclass
class EditParams:
    """État d'édition : liste de presets EMPILÉS + 8 curseurs (-100..100, 0 neutre).

    presets = une base (Naturel ou Noir & Blanc) + 0..N looks créatifs.
    Ex. ["Naturel", "Cinématique"] = correction v3 puis grade cinéma.
    """
    presets:     list  = field(default_factory=lambda: [DEFAULT_PRESET])
    exposure:    float = 0.0
    contrast:    float = 0.0
    highlights:  float = 0.0
    shadows:     float = 0.0
    temperature: float = 0.0
    tint:        float = 0.0
    vibrance:    float = 0.0
    saturation:  float = 0.0
    clarity:     float = 0.0
    sharpness:   float = 0.0
    vignette:    float = 0.0
    grain:       float = 0.0

    def is_neutral(self) -> bool:
        """True si presets == [Naturel] et tous les curseurs à 0 (= v3 strict)."""
        return list(self.presets) == [DEFAULT_PRESET] and self._sliders_zero()

    def _sliders_zero(self) -> bool:
        return all(getattr(self, n) == 0.0 for n in _SLIDER_NAMES)

    def base(self) -> str:
        return "Noir & Blanc" if "Noir & Blanc" in self.presets else "Naturel"

    def looks(self) -> list:
        return [p for p in LOOK_PRESETS if p in self.presets]

    def label(self) -> str:
        return " + ".join(self.presets) if self.presets else "Original"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["presets"] = list(self.presets)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EditParams":
        if not d:
            return cls()
        known = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in known}
        if "presets" in kw and not kw["presets"]:
            kw["presets"] = [DEFAULT_PRESET]
        # rétro-compat : ancien champ unique « preset »
        if "presets" not in kw and "preset" in d:
            kw["presets"] = [d["preset"]]
        return cls(**kw)


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


def _tint(arr, v):               # + = magenta, - = vert
    if v:
        t = v / 100.0
        arr[:, :, 1] *= 1.0 - 0.12 * t
        arr[:, :, 0] *= 1.0 + 0.04 * t
        arr[:, :, 2] *= 1.0 + 0.04 * t
    return arr


def _vibrance(arr, v):           # saturation qui protège les zones déjà saturées (peau)
    if v:
        lum = _luma(arr)[:, :, None]
        mx = arr.max(axis=2, keepdims=True)
        mn = arr.min(axis=2, keepdims=True)
        sat = (mx - mn) / (mx + 1e-6)
        factor = 1.0 + (v / 100.0) * (1.0 - sat)
        arr[:] = lum + (arr - lum) * factor
    return arr


def _clarity(arr, v):            # contraste local des mi-tons (+net / -doux peau)
    if v:
        blurred = _gaussian(arr, radius=12)
        lum = _luma(arr)[:, :, None]
        mid = np.clip(1.0 - np.abs(lum - 0.5) * 2.0, 0, 1)   # poids mi-tons
        arr += (v / 100.0) * 0.7 * (arr - blurred) * mid
    return arr


def _vignette(arr, v):           # + assombrit les coins, - les éclaircit
    if v:
        h, w = arr.shape[:2]
        yy, xx = np.ogrid[:h, :w]
        cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
        d = np.sqrt(((xx - cx) / (cx + 1e-6)) ** 2 + ((yy - cy) / (cy + 1e-6)) ** 2)
        mask = (np.clip(d / 1.41, 0, 1) ** 2)[:, :, None].astype(np.float32)
        arr *= (1.0 - (v / 100.0) * 0.6 * mask)
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
    """Applique les corrections manuelles, en place, dans l'ORDRE PRO :

    1. lumière (exposition, hautes lumières, ombres)
    2. balance des blancs (température, teinte)
    3. contraste
    4. correction colorimétrique (vibrance, saturation = TSL)
    5. contraste local (clarté)
    6. touches finales (netteté, vignettage, grain)
    """
    _exposure(arr, p.exposure)          # 1. lumière
    _highlights(arr, p.highlights)
    _shadows(arr, p.shadows)
    _temperature(arr, p.temperature)    # 2. balance des blancs
    _tint(arr, p.tint)
    _contrast(arr, p.contrast)          # 3. contraste
    _vibrance(arr, p.vibrance)          # 4. couleur (TSL)
    _saturation(arr, p.saturation)
    _clarity(arr, p.clarity)            # 5. contraste local
    _sharpness(arr, p.sharpness)        # 6. touches finales
    _vignette(arr, p.vignette)
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


def look_clair_aere(arr01: np.ndarray) -> np.ndarray:
    """Light & airy : lumineux, doux, noirs levés, légèrement chaud."""
    out = arr01.copy()
    out *= 0.88; out += 0.09                          # lève les noirs (matte)
    out -= 0.5; out *= 0.92; out += 0.5               # contraste réduit
    out[:, :, 0] *= 1.02                              # chaleur légère
    out[:, :, 2] *= 0.99
    lum = _luma(out)[:, :, None]
    out[:] = lum + (out - lum) * 0.95                 # désat très légère
    np.clip(out, 0, 1, out=out)
    return out


def look_peau_douce(arr01: np.ndarray) -> np.ndarray:
    """Portrait doux : léger lissage global + chaleur de peau."""
    out = arr01.copy()
    blurred = _gaussian(out, radius=8)
    out = out * 0.72 + blurred * 0.28                 # adoucit (clarté négative)
    out[:, :, 0] *= 1.03                              # peau plus chaude
    out[:, :, 2] *= 0.98
    np.clip(out, 0, 1, out=out)
    return out


_LOOKS = {
    "Naturel":      look_naturel,
    "Cinématique":  look_cinematique,
    "Noir & Blanc": look_bw,
    "Clair & Aéré": look_clair_aere,
    "Peau douce":   look_peau_douce,
    "Vintage":      look_vintage,
    "Golden Hour":  look_golden,
    "Froid":        look_froid,
}


# ── Rendu unifié ──────────────────────────────────────────────────────────────

def render_with_profile(arr01: np.ndarray, params: EditParams,
                        profile: dict = None, grain_seed=None,
                        lut_engine=None, lut_name=None, lut_strength=1.0,
                        vibrance=0.0) -> np.ndarray:
    """Rendu unifié : base (Naturel/N&B) PUIS looks empilés PUIS corrections.

    - base « Naturel » : étalonnage v3, piloté par le profil dossier si fourni
      (rendu uniforme sur la série) ; sinon métriques par image.
    - base « Noir & Blanc » : conversion N&B.
    - look créatif (Cinématique) appliqué par-dessus la base.
    - puis les 8 corrections manuelles.
    """
    # Aucun preset sélectionné → image ORIGINALE (aucun étalonnage), seules
    # les corrections manuelles éventuelles s'appliquent. C'est l'état rendu
    # par « Réinitialiser tous les réglages ».
    if not params.presets:
        out = arr01.copy()
        if not params._sliders_zero():
            out = apply_manual(out, params, grain_seed=grain_seed)
        return _apply_lut_vibrance(out, lut_engine, lut_name, lut_strength, vibrance)

    base = params.base()
    if base == "Noir & Blanc":
        out = look_bw(arr01)
    else:
        arr255 = arr01 * 255.0
        if is_grayscale(arr255):
            out = np.asarray(apply_bw_grade(arr01.copy()), dtype=np.float32) / 255.0
        else:
            m = profile if profile else analyze_image(arr01)
            out = np.asarray(apply_color_grade(arr01.copy(), m), dtype=np.float32) / 255.0

    for look in params.looks():
        out = _LOOKS[look](out)

    if not params.is_neutral():
        out = apply_manual(out, params, grain_seed=grain_seed)

    # LUT 3D + vibrance, en dernier (cohérent avec le chemin v3, étape 8)
    return _apply_lut_vibrance(out, lut_engine, lut_name, lut_strength, vibrance)


def _apply_lut_vibrance(out, lut_engine, lut_name, lut_strength, vibrance):
    """Applique LUT (si fournie) puis vibrance (si non nulle). N&B exclu de la LUT."""
    if lut_engine and lut_name:
        out = lut_engine.apply(out, lut_name, lut_strength)
    if vibrance:
        from core.lut_engine import apply_vibrance
        out = apply_vibrance(out, vibrance)
    return np.clip(out, 0, 1)


def render(arr01: np.ndarray, params: EditParams, grain_seed=None) -> np.ndarray:
    """Rendu sans profil de série (aperçu simple). Retourne un array 0..1."""
    return render_with_profile(arr01, params, profile=None, grain_seed=grain_seed)


def render_to_image(arr01: np.ndarray, params: EditParams, grain_seed=None) -> Image.Image:
    out = render(arr01, params, grain_seed=grain_seed)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
