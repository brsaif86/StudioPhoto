"""Tests du moteur few-shot (entraînement + inférence) avec un embedder factice."""
import numpy as np
import pytest
from PIL import Image

from core.fewshot import (
    _train_logreg, _predict, train_from_folders, save_model, load_model,
    model_info, FewShotClassifier,
)


# ── Embedder factice : projette la couleur moyenne dans un espace D ───────────

class StubEmbedder:
    """Imite core.classification.Classifier pour les tests (pas d'ONNX)."""
    input_size = 8
    mean = [0.0, 0.0, 0.0]
    std = [1.0, 1.0, 1.0]
    _P = np.random.default_rng(0).standard_normal((3, 16)).astype(np.float32)

    def forward(self, blob):                         # blob [n,3,H,W] en 0..1
        m = blob.reshape(blob.shape[0], 3, -1).mean(axis=2)   # [n,3]
        return (m @ self._P).astype(np.float32)               # [n,16]


_COLORS = {                                          # 3 catégories = 3 couleurs nettes
    "Dance":      (220, 40, 40),
    "Family":     (40, 200, 60),
    "Atmosphere": (40, 60, 220),
}


def _make_dataset(root, n_per=6):
    for cat, rgb in _COLORS.items():
        d = root / cat
        d.mkdir(parents=True)
        for i in range(n_per):
            arr = np.full((16, 16, 3), rgb, np.uint8)
            arr[:2, :2] = (i * 7) % 255            # léger bruit déterministe
            Image.fromarray(arr).save(str(d / f"{i}.jpg"), quality=92)


# ── Régression logistique pure ────────────────────────────────────────────────

def test_logreg_separable():
    rng = np.random.default_rng(1)
    centers = np.array([[3, 0, 0], [0, 3, 0], [0, 0, 3]], np.float32)
    X = np.repeat(centers, 30, axis=0) + 0.05 * rng.standard_normal((90, 3)).astype(np.float32)
    y = np.repeat([0, 1, 2], 30)
    W, b = _train_logreg(X, y, 3)
    acc = (_predict(X, W, b).argmax(1) == y).mean()
    assert acc > 0.98


# ── Entraînement depuis des dossiers ──────────────────────────────────────────

def test_train_from_folders(tmp_path):
    _make_dataset(tmp_path)
    res = train_from_folders(tmp_path, StubEmbedder(), on_log=lambda *_: None)
    assert set(res["labels"]) == set(_COLORS)
    assert res["n"] == 6 * len(_COLORS)
    assert res["W"].shape == (3, 16)
    # données nettement séparables → précision validation élevée
    assert res["acc"] > 0.8


def test_train_requires_two_classes(tmp_path):
    (tmp_path / "Solo").mkdir()
    for i in range(4):
        Image.fromarray(np.full((16, 16, 3), (10, 10, 10), np.uint8)).save(
            str(tmp_path / "Solo" / f"{i}.jpg"))
    with pytest.raises(RuntimeError):
        train_from_folders(tmp_path, StubEmbedder(), on_log=lambda *_: None)


# ── Persistance + inférence ───────────────────────────────────────────────────

def test_save_load_and_classify(tmp_path):
    _make_dataset(tmp_path)
    res = train_from_folders(tmp_path, StubEmbedder(), on_log=lambda *_: None)
    model_path = tmp_path / "model.npz"
    save_model(res, model_path)

    loaded = load_model(model_path)
    assert loaded["labels"] == res["labels"]
    np.testing.assert_allclose(loaded["W"], res["W"], atol=1e-5)

    info = model_info(model_path)
    assert info["n"] == res["n"] and len(info["labels"]) == 3

    # une nouvelle image « Dance » (rouge) doit être classée Dance
    clf = FewShotClassifier.from_model(StubEmbedder(), loaded)
    test_img = tmp_path / "query.jpg"
    Image.fromarray(np.full((16, 16, 3), (220, 40, 40), np.uint8)).save(str(test_img))
    out = clf.classify_paths([str(test_img)])
    assert len(out) == 1 and "error" not in out[0]
    assert clf.labels[out[0]["idx"]] == "Dance"
    assert out[0]["confidence"] > 0.5


def test_classify_paths_handles_bad_path(tmp_path):
    _make_dataset(tmp_path)
    res = train_from_folders(tmp_path, StubEmbedder(), on_log=lambda *_: None)
    clf = FewShotClassifier.from_model(StubEmbedder(), res)
    out = clf.classify_paths([str(tmp_path / "n_existe_pas.jpg")])
    assert len(out) == 1 and "error" in out[0]


def test_load_model_absent(tmp_path):
    assert load_model(tmp_path / "rien.npz") is None
    assert model_info(tmp_path / "rien.npz") is None
