import numpy as np
import pytest
from pathlib import Path
from PIL import Image
from core.lut_engine import load_cube_lut, apply_lut, apply_vibrance, LutEngine
from core.grading import process_image
import cv2

def create_identity_cube(path: Path, size: int = 2):
    """Crée un fichier .cube identité (simple mapping 0..1)."""
    with path.open("w", encoding="utf-8") as f:
        f.write(f"LUT_3D_SIZE {size}\n")
        # Pour une LUT identité, la valeur est simplement l'indice / (size-1)
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    f.write(f"{r/(size-1):.6f} {g/(size-1):.6f} {b/(size-1):.6f}\n")

def test_load_cube_lut_valid(tmp_path):
    lut_path = tmp_path / "identity.cube"
    create_identity_cube(lut_path, 2)
    lut, size = load_cube_lut(lut_path)
    assert size == 2
    assert lut.shape == (2, 2, 2, 3)
    assert np.allclose(lut[0, 0, 0], [0, 0, 0])
    assert np.allclose(lut[1, 1, 1], [1, 1, 1])


def test_load_cube_red_stays_red(tmp_path):
    """Bug R/B : une LUT identité chargée d'un .cube ne doit PAS permuter R et B."""
    lut_path = tmp_path / "identity.cube"
    create_identity_cube(lut_path, 4)
    lut, size = load_cube_lut(lut_path)
    # rouge pur, vert pur, bleu pur → inchangés par une identité
    img = np.array([[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]], dtype=np.float32)
    out = apply_lut(img, lut, size)
    np.testing.assert_allclose(out, img, atol=1e-5)

def test_apply_lut_identity():
    size = 2
    lut = np.zeros((2, 2, 2, 3), dtype=np.float32)
    for b in range(2):
        for g in range(2):
            for r in range(2):
                lut[r, g, b] = [r/1, g/1, b/1]

    img = np.random.rand(100, 100, 3).astype(np.float32)
    res = apply_lut(img, lut, size)

    # RMSE < 0.001
    rmse = np.sqrt(np.mean((img - res)**2))
    assert rmse < 0.001

def test_apply_lut_interpolation():
    # LUT 2x2x2 : 0 -> 0, 1 -> 1.
    # Au centre (0.5, 0.5, 0.5), on doit avoir (0.5, 0.5, 0.5)
    size = 2
    lut = np.zeros((2, 2, 2, 3), dtype=np.float32)
    for b in range(2):
        for g in range(2):
            for r in range(2):
                lut[r, g, b] = [r, g, b]

    img = np.full((1, 1, 3), 0.5, dtype=np.float32)
    res = apply_lut(img, lut, size)
    assert np.allclose(res, 0.5)

def test_apply_vibrance_neutral():
    img = np.random.rand(100, 100, 3).astype(np.float32)
    res = apply_vibrance(img, 0.0)
    assert np.allclose(img, res)

def test_apply_vibrance_boost():
    # Créer une image grisâtre (faible saturation)
    img = np.full((100, 100, 3), 0.5, dtype=np.float32)
    img[:, :, 0] += 0.1 # un peu de rouge

    res = apply_vibrance(img, 0.3)

    # On compare la saturation moyenne (en HSV)
    def get_avg_sat(image):
        uint8 = (image * 255).astype(np.uint8)
        hsv = cv2.cvtColor(uint8, cv2.COLOR_RGB2HSV)
        return np.mean(hsv[..., 1])

    assert get_avg_sat(res) > get_avg_sat(img)

def test_lut_engine_cache(tmp_path):
    lut_path = tmp_path / "test.cube"
    create_identity_cube(lut_path)

    engine = LutEngine(str(tmp_path))

    import core.lut_engine as le
    from unittest.mock import patch

    with patch('core.lut_engine.load_cube_lut', wraps=le.load_cube_lut) as spy:
        engine.apply(np.zeros((10,10,3), np.float32), "test.cube")
        engine.apply(np.zeros((10,10,3), np.float32), "test.cube")
        assert spy.call_count == 1


def test_lut_cache_across_instances(tmp_path):
    """Le cache doit tenir même avec une NOUVELLE LutEngine par image (cas du lot)."""
    create_identity_cube(tmp_path / "x.cube")
    import core.lut_engine as le
    from unittest.mock import patch
    le._load_lut_cached.cache_clear()
    img = np.zeros((8, 8, 3), np.float32)
    with patch('core.lut_engine.load_cube_lut', wraps=le.load_cube_lut) as spy:
        for _ in range(5):                       # 5 « images », instance neuve à chaque fois
            LutEngine(str(tmp_path)).apply(img, "x.cube", 1.0)
        assert spy.call_count == 1               # .cube lu une seule fois

def test_lut_strength_blend():
    size = 2
    lut = np.zeros((2, 2, 2, 3), dtype=np.float32)
    for b in range(2):
        for g in range(2):
            for r in range(2):
                lut[r, g, b] = [r, g, b]

    # On crée une LUT qui inverse les couleurs pour bien voir le blend
    lut = 1.0 - lut

    img = np.full((10, 10, 3), 0.2, dtype=np.float32)

    # Mock LutEngine
    from core.lut_engine import LutEngine
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        lut_path = Path(tmp) / "inv.cube"
        # On écrit la LUT inversée
        with lut_path.open("w") as f:
            f.write("LUT_3D_SIZE 2\n")
            for b in range(2):
                for g in range(2):
                    for r in range(2):
                        f.write(f"{1-r:.6f} {1-g:.6f} {1-b:.6f}\n")

        engine = LutEngine(tmp)

        # strength = 0 -> original
        res0 = engine.apply(img, "inv.cube", 0.0)
        assert np.allclose(res0, img)

        # strength = 1 -> full LUT
        res1 = engine.apply(img, "inv.cube", 1.0)
        # 0.2 -> index 0.2*1 = 0.2.
        # Interp: 0.8 * (1) + 0.2 * (0) = 0.8
        assert np.allclose(res1, 0.8)

def test_no_regression_without_lut(tmp_path):
    """Sans LUT, process_image doit produire EXACTEMENT le v3 (apply_color_grade).

    Aucune écriture hors de tmp_path (pas de pollution d'assets/).
    """
    from core.grading import apply_color_grade, analyze_image

    # image synthétique (ton chair typique) sauvée en JPEG q95 sans sous-éch.
    arr = np.full((96, 96, 3), [160, 130, 110], dtype=np.uint8)
    src = tmp_path / "in.jpg"
    Image.fromarray(arr).save(str(src), quality=95, subsampling=0)
    dst = tmp_path / "out.jpg"

    msg = process_image(src, dst, skip_existing=False, lut_engine=None)
    assert "✓" in msg and dst.exists()

    # Référence : v3 direct sur la même image décodée
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32) / 255.0
    ref = np.asarray(apply_color_grade(a.copy(), analyze_image(a)), dtype=np.float32)
    out = np.asarray(Image.open(dst).convert("RGB"), dtype=np.float32)

    rmse = float(np.sqrt(np.mean((out - ref) ** 2)))
    assert rmse < 2.0, f"Régression : RMSE={rmse:.2f}"
