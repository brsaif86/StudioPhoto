"""
tests/test_classification.py — Tests du moteur de tri auto zero-shot
====================================================================
Aucun asset ONNX réel requis : on injecte un faux réseau (forward stub).
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.classification import (
    CLASSES, LABELS, TEMPLATES, REVIEW_LABEL, DEFAULT_THRESHOLD,
    preprocess, softmax_confidence, category_for,
    collect_images, write_manifest, Classifier,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_jpg(path: Path, color=(120, 90, 70), size=(64, 64)) -> None:
    Image.new("RGB", size, color).save(str(path), quality=90)


class FakeClassifier(Classifier):
    """Classifier sans ONNX : forward renvoie des features déterministes."""
    def __init__(self, dim=8, n_classes=6):
        super().__init__(assets_dir=Path("."))
        rng = np.random.default_rng(0)
        self._meta = {
            "input_size": 32, "mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5],
            "logit_scale": 100.0, "labels": LABELS,
        }
        te = rng.standard_normal((n_classes, dim)).astype(np.float32)
        self._text_emb = te / np.linalg.norm(te, axis=1, keepdims=True)
        self._dim = dim

    def forward(self, blob):
        # une feature par image du batch, dérivée du contenu (déterministe)
        n = blob.shape[0]
        rng = np.random.default_rng(int(abs(blob.sum())) % 9999)
        return rng.standard_normal((n, self._dim)).astype(np.float32)


# ── preprocess ────────────────────────────────────────────────────────────────

def test_preprocess_shape_dtype():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "a.jpg"
        make_jpg(p)
        blob = preprocess(p, 32, [0.5, 0.5, 0.5], [0.5, 0.5, 0.5])
        assert blob.shape == (1, 3, 32, 32)
        assert blob.dtype == np.float32


def test_preprocess_deterministic():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "a.jpg"
        make_jpg(p)
        b1 = preprocess(p, 32, [0.5]*3, [0.5]*3)
        b2 = preprocess(p, 32, [0.5]*3, [0.5]*3)
        np.testing.assert_array_equal(b1, b2)


def test_preprocess_corrupt_raises():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "bad.jpg"
        p.write_bytes(b"not an image")
        with pytest.raises(Exception):
            preprocess(p, 32, [0.5]*3, [0.5]*3)


# ── softmax / confiance ───────────────────────────────────────────────────────

def test_softmax_sums_to_one():
    feat = np.random.RandomState(1).randn(3, 8).astype(np.float32)
    emb = np.random.RandomState(2).randn(6, 8).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    _, _, probs = softmax_confidence(feat, emb, 100.0)
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-5)


def test_logit_scale_sharpens():
    feat = np.random.RandomState(3).randn(1, 8).astype(np.float32)
    emb = np.random.RandomState(4).randn(6, 8).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    _, conf_low, _  = softmax_confidence(feat, emb, 1.0)
    _, conf_high, _ = softmax_confidence(feat, emb, 100.0)
    # Un logit_scale élevé concentre la proba sur la meilleure classe
    assert conf_high[0] >= conf_low[0]


# ── mapping / seuil ───────────────────────────────────────────────────────────

def test_category_mapping_order():
    for i, name in enumerate(LABELS):
        assert category_for(i, 0.99, 0.45) == name


def test_threshold_review():
    assert category_for(0, 0.10, 0.45) == REVIEW_LABEL
    assert category_for(0, 0.90, 0.45) == LABELS[0]


def test_labels_match_classes_order():
    assert LABELS == list(CLASSES.keys())
    assert len(LABELS) == 6


# ── classify_paths : isolation des erreurs ────────────────────────────────────

def test_classify_paths_isolates_corrupt():
    clf = FakeClassifier()
    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.jpg"
        bad  = Path(tmp) / "bad.jpg"
        make_jpg(good)
        bad.write_bytes(b"broken")
        res = clf.classify_paths([good, bad])
        by_name = {Path(r["path"]).name: r for r in res}
        assert "error" in by_name["bad.jpg"]          # corrompu isolé
        assert "idx" in by_name["good.jpg"]           # valide classé
        assert 0.0 <= by_name["good.jpg"]["confidence"] <= 1.0


# ── manifest ──────────────────────────────────────────────────────────────────

def test_write_manifest_json_sorted():
    rows = [
        {"path": "a.jpg", "category": "Dance", "confidence": 0.40},
        {"path": "b.jpg", "category": "Family", "confidence": 0.95},
        {"path": "c.jpg", "category": "Atmosphere", "confidence": 0.70},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        write_manifest(rows, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        confs = [r["confidence"] for r in data]
        assert confs == sorted(confs, reverse=True)   # tri décroissant


def test_write_manifest_csv():
    rows = [{"path": "a.jpg", "category": "Dance", "confidence": 0.42}]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.csv"
        write_manifest(rows, out)
        text = out.read_text(encoding="utf-8")
        assert "path,category,confidence" in text
        assert "Dance" in text


# ── collecte ──────────────────────────────────────────────────────────────────

def test_collect_images_excludes_category_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        make_jpg(base / "p1.jpg")
        (base / "Dance").mkdir()
        make_jpg(base / "Dance" / "already.jpg")        # déjà trié → exclu
        (base / REVIEW_LABEL).mkdir()
        make_jpg(base / REVIEW_LABEL / "r.jpg")          # à revoir → exclu
        files = collect_images(base, recursive=True)
        names = [p.name for p in files]
        assert "p1.jpg" in names
        assert "already.jpg" not in names
        assert "r.jpg" not in names
