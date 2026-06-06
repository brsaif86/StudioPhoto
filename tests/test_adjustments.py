"""
tests/test_adjustments.py — Moteur d'édition v3.0
"""

import numpy as np
import pytest
from PIL import Image

from core.grading import analyze_image, apply_color_grade
from core.adjustments import (
    EditParams, PRESETS, DEFAULT_PRESET, render, render_to_image, apply_manual,
)


def patch(r, g, b, size=(48, 48)):
    return np.full((*size, 3), [r, g, b], dtype=np.float32)


# ── Neutralité : Naturel + 0 == v3 strict ─────────────────────────────────────

def test_natural_zero_equals_v3():
    arr = patch(0.62, 0.50, 0.42)
    m = analyze_image(arr.copy())
    v3 = np.asarray(apply_color_grade(arr.copy(), m), dtype=np.float32) / 255.0
    out = render(arr, EditParams())          # preset Naturel, tous curseurs 0
    np.testing.assert_allclose(out, v3, atol=1e-6)


def test_editparams_is_neutral():
    assert EditParams().is_neutral()
    assert not EditParams(exposure=10).is_neutral()
    assert not EditParams(presets=["Vintage"]).is_neutral()
    assert not EditParams(presets=["Naturel", "Cinématique"]).is_neutral()


# ── Sérialisation ─────────────────────────────────────────────────────────────

def test_editparams_roundtrip():
    p = EditParams(presets=["Naturel", "Cinématique"], exposure=15, grain=20)
    d = p.to_dict()
    p2 = EditParams.from_dict(d)
    assert p2 == p
    assert EditParams.from_dict({}) == EditParams()
    # clés inconnues ignorées
    assert EditParams.from_dict({"exposure": 5, "inconnu": 9}).exposure == 5
    # rétro-compat ancien champ « preset »
    assert EditParams.from_dict({"preset": "Vintage"}).presets == ["Vintage"]


# ── Presets combinés ──────────────────────────────────────────────────────────

def test_combine_two_presets():
    arr = patch(0.55, 0.45, 0.40)
    out = render(arr, EditParams(presets=["Naturel", "Cinématique"]))
    assert out.shape == arr.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


# ── Tous les presets : sortie valide en 0..1 ──────────────────────────────────

@pytest.mark.parametrize("preset", PRESETS)
def test_preset_in_range(preset):
    arr = patch(0.55, 0.45, 0.40)
    out = render(arr, EditParams(presets=[preset]))
    assert out.shape == arr.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_bw_is_grayscale():
    arr = patch(0.70, 0.30, 0.20)
    out = render(arr, EditParams(presets=["Noir & Blanc"]))
    # canaux égaux → image neutre
    assert np.allclose(out[..., 0], out[..., 1], atol=1e-3)
    assert np.allclose(out[..., 1], out[..., 2], atol=1e-3)


# ── Corrections manuelles ─────────────────────────────────────────────────────

def test_exposure_brightens():
    arr = patch(0.4, 0.4, 0.4)
    base = render(arr, EditParams())
    bright = render(arr, EditParams(exposure=40))
    assert bright.mean() > base.mean()


def test_saturation_zero_is_noop_on_manual():
    arr = patch(0.6, 0.4, 0.3)
    a = arr.copy()
    apply_manual(a, EditParams())            # tous 0
    np.testing.assert_allclose(a, arr, atol=1e-6)


def test_temperature_warm_increases_red():
    arr = patch(0.5, 0.5, 0.5)
    warm = render(arr, EditParams(temperature=60))
    # plus chaud → R > B
    assert warm[..., 0].mean() > warm[..., 2].mean()


def test_grain_adds_variation():
    arr = patch(0.5, 0.5, 0.5)
    flat = render(arr, EditParams())
    grainy = render(arr, EditParams(grain=60), grain_seed=1)
    assert grainy.std() > flat.std()


def test_render_to_image_type():
    arr = patch(0.5, 0.45, 0.4)
    img = render_to_image(arr, EditParams(presets=["Vintage"]))
    assert isinstance(img, Image.Image)
    assert img.size == (48, 48)
