"""
tests/test_grading.py — Tests de correction de l'étalonnage v3
===============================================================
Vérifie que l'algorithme n'a pas dérivé par rapport à la référence.
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.grading import (
    apply_bw_grade,
    apply_color_grade,
    analyze_image,
    is_grayscale,
    process_image,
    collect_grade_tasks,
    compute_folder_profile,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_image(r, g, b, size=(64, 64)) -> Image.Image:
    arr = np.full((*size, 3), [r, g, b], dtype=np.uint8)
    return Image.fromarray(arr)


def arr01(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


# ── is_grayscale ──────────────────────────────────────────────────────────────

def test_grayscale_detected():
    arr = np.full((32, 32, 3), 128, dtype=np.float32)
    assert is_grayscale(arr)


def test_color_not_grayscale():
    arr = np.zeros((32, 32, 3), dtype=np.float32)
    arr[:, :, 0] = 200   # rouge dominant
    arr[:, :, 1] = 100
    arr[:, :, 2] = 50
    assert not is_grayscale(arr)


# ── analyze_image ─────────────────────────────────────────────────────────────

def test_analyze_returns_keys():
    img = make_image(128, 100, 80)
    m = analyze_image(arr01(img))
    for k in ("mean_lum", "std_lum", "warm_cast", "highlight_ratio"):
        assert k in m


def test_analyze_warm_cast_positive():
    img = make_image(200, 100, 50)   # dominante chaude
    m = analyze_image(arr01(img))
    assert m["warm_cast"] > 0


def test_analyze_highlight_ratio_bright():
    img = make_image(240, 240, 240)
    m = analyze_image(arr01(img))
    assert m["highlight_ratio"] > 0.9


# ── apply_color_grade ─────────────────────────────────────────────────────────

def test_color_grade_output_in_range():
    img = make_image(150, 120, 100)
    a = arr01(img)
    m = analyze_image(a.copy())
    result = apply_color_grade(a, m)
    out = np.asarray(result, dtype=np.float32) / 255.0
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_color_grade_not_identical_to_input():
    img = make_image(150, 120, 100)
    a = arr01(img)
    m = analyze_image(a.copy())
    # apply_color_grade modifie arr in-place — comparer avant/après
    a_copy = arr01(img)   # copie fraîche
    result = apply_color_grade(a_copy, m)
    original = np.asarray(img, dtype=np.float32) / 255.0
    assert not np.allclose(np.asarray(result, dtype=np.float32) / 255.0, original, atol=1e-3)


def test_color_grade_deterministic():
    """Même image → même résultat (pas de randomness)."""
    img = make_image(160, 130, 110)

    a1 = arr01(img)
    m1 = analyze_image(a1.copy())
    r1 = np.asarray(apply_color_grade(a1, m1), dtype=np.float32)

    a2 = arr01(img)
    m2 = analyze_image(a2.copy())
    r2 = np.asarray(apply_color_grade(a2, m2), dtype=np.float32)

    np.testing.assert_array_equal(r1, r2)


# ── apply_bw_grade ────────────────────────────────────────────────────────────

def test_whites_stay_neutral():
    """Une zone blanche/quasi-blanche ne doit prendre AUCUNE dominante (robe).

    Garantit que l'étalonnage ne fait pas virer le blanc vers le bleu.
    """
    for level in (0.88, 0.92, 0.96):
        white = np.full((48, 48, 3), level, dtype=np.float32)
        m = analyze_image(white.copy())
        out = np.asarray(apply_color_grade(white.copy(), m), dtype=np.float32) / 255.0
        r, g, b = out[..., 0].mean(), out[..., 1].mean(), out[..., 2].mean()
        # Écart entre canaux quasi nul → pas de teinte
        assert abs(b - r) < 0.01, f"Cast bleu sur blanc {level}: B-R={b - r:+.4f}"
        assert abs(r - g) < 0.01, f"Cast sur blanc {level}: R-G={r - g:+.4f}"


def test_bright_image_not_overexposed():
    """Une image déjà lumineuse ne doit pas être encore éclaircie (anti-surexpo)."""
    bright = np.full((40, 40, 3), 0.93, dtype=np.float32)
    m = analyze_image(bright.copy())
    out = np.asarray(apply_color_grade(bright.copy(), m), dtype=np.float32) / 255.0
    # La sortie ne doit pas dépasser l'entrée (pas d'ouverture des hautes lumières)
    assert out.mean() <= 0.932, f"Image éclaircie : {out.mean():.3f} > 0.93"


def test_coherent_profile_average():
    """compute_folder_profile renvoie la moyenne des métriques d'une série."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, lvl in enumerate((90, 140, 190)):   # sombre, moyen, clair
            p = Path(tmp) / f"img_{i}.jpg"
            make_image(lvl, lvl - 20, lvl - 40, size=(80, 80)).save(str(p), quality=95)
            paths.append(p)
        prof = compute_folder_profile(paths)
        assert prof is not None
        for k in ("mean_lum", "std_lum", "warm_cast", "highlight_ratio"):
            assert k in prof
        # mean_lum du profil ≈ moyenne des 3 niveaux (autour du niveau médian)
        assert 0.3 < prof["mean_lum"] < 0.75


def test_bw_grade_output_in_range():
    img = make_image(100, 100, 100)
    a = arr01(img)
    result = apply_bw_grade(a)
    out = np.asarray(result, dtype=np.float32) / 255.0
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_bw_grade_lifts_shadows():
    """Le shadow lift doit éclaircir les noirs."""
    img = make_image(0, 0, 0)
    a = arr01(img)
    result = apply_bw_grade(a)
    out_mean = np.asarray(result, dtype=np.float32).mean()
    assert out_mean > 0   # noir pur → légèrement plus clair


# ── process_image ─────────────────────────────────────────────────────────────

def test_process_image_creates_file():
    img = make_image(150, 120, 100, size=(128, 128))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.jpg"
        img.save(str(src), quality=95)

        dst = Path(tmp) / "test_graded.jpg"
        msg = process_image(src, dst, skip_existing=False)

        assert dst.exists()
        assert "✓" in msg


def test_process_image_skip():
    img = make_image(150, 120, 100, size=(64, 64))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "test.jpg"
        dst = Path(tmp) / "test_graded.jpg"
        img.save(str(src), quality=95)
        dst.touch()   # simuler fichier déjà traité

        msg = process_image(src, dst, skip_existing=True)
        assert "⏭" in msg


def test_process_image_corrupted():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "bad.jpg"
        src.write_bytes(b"not an image")
        dst = Path(tmp) / "bad_graded.jpg"

        msg = process_image(src, dst, skip_existing=False)
        assert "✗" in msg
        assert not dst.exists()


# ── collect_grade_tasks ───────────────────────────────────────────────────────

def test_collect_tasks_excludes_output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "_output").mkdir()
        (tmp_path / "_output" / "skip_me.jpg").touch()
        (tmp_path / "real.jpg").touch()

        tasks = collect_grade_tasks(tmp_path, "_graded", None, False, False)
        paths = [t[0] for t in tasks]
        assert not any("_output" in p for p in paths)
        assert any("real.jpg" in p for p in paths)


def test_collect_tasks_excludes_mac_dotfiles():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "._thumbs.jpg").touch()
        (tmp_path / "good.jpg").touch()

        tasks = collect_grade_tasks(tmp_path, "_graded", None, False, False)
        paths = [t[0] for t in tasks]
        assert not any("._" in Path(p).name for p in paths)


def test_collect_tasks_excludes_already_graded():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "photo_graded.jpg").touch()
        (tmp_path / "photo.jpg").touch()

        tasks = collect_grade_tasks(tmp_path, "_graded", None, False, False)
        paths = [t[0] for t in tasks]
        assert not any("_graded" in Path(p).stem for p in paths)


# ── Test de correction : comparaison pixel avec image de référence ─────────────

def test_regression_color_grade(tmp_path):
    """Génère une sortie et vérifie qu'elle correspond à la référence stockée.

    La première exécution génère la référence ; les suivantes comparent.
    Tolérance : ≤ 2 niveaux de gris (sur 255) en RMSE.
    """
    img = make_image(160, 130, 110, size=(64, 64))
    a = arr01(img)
    m = analyze_image(a.copy())
    result = apply_color_grade(a, m)

    ref_path = Path(__file__).parent / "ref_color_grade.png"
    if not ref_path.exists():
        result.save(str(ref_path))
        pytest.skip("Référence créée — relance le test pour valider.")

    ref = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.float32)
    out = np.asarray(result, dtype=np.float32)
    rmse = float(np.sqrt(np.mean((ref - out) ** 2)))
    assert rmse < 2.0, f"RMSE={rmse:.2f} — l'algorithme a dérivé !"
