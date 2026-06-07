"""Tests du backend Ollama (mockés : aucun serveur requis)."""
import numpy as np
import pytest
from PIL import Image

from core import ollama_classify as oc
from core import classification as C


def test_parse_json_robuste():
    assert oc._parse_json('{"a": 1}') == {"a": 1}
    assert oc._parse_json('blabla {"category": "Dance", "confidence": 0.5} fin')["category"] == "Dance"
    assert oc._parse_json("pas du json") == {}
    assert oc._parse_json("") == {}


def test_schema_enum_couvre_labels():
    sch = oc.output_schema()
    assert sch["properties"]["category"]["enum"] == list(oc.LABELS)
    assert "confidence" in sch["required"]


def test_prompt_mentionne_chaque_categorie():
    prompt = oc.build_prompt()
    for lab in oc.LABELS:
        assert lab in prompt


def test_resolve_model(monkeypatch):
    monkeypatch.setattr(oc, "list_models",
                        lambda url=oc.DEFAULT_URL, timeout=5.0: ["gemma4:latest", "qwen3.5:latest"])
    monkeypatch.setattr(oc, "supports_vision",
                        lambda m, url=oc.DEFAULT_URL, timeout=8.0: m.startswith("gemma"))
    assert oc.resolve_model("gemma4:latest") == "gemma4:latest"      # exact
    assert oc.resolve_model("gemma4") == "gemma4:latest"             # même base
    assert oc.resolve_model("introuvable:1b") == "gemma4:latest"     # repli vision
    monkeypatch.setattr(oc, "list_models", lambda url=oc.DEFAULT_URL, timeout=5.0: [])
    assert oc.resolve_model("gemma4:latest") is None                 # rien d'installé


def _clf(monkeypatch, response: dict):
    monkeypatch.setattr(oc, "_encode_image", lambda p, max_side=None: "b64data")
    clf = oc.OllamaClassifier("gemma4:latest")
    clf.model = "gemma4:latest"
    monkeypatch.setattr(clf, "_generate", lambda b64: response)
    return clf


def test_classify_one_mappe_label(monkeypatch):
    clf = _clf(monkeypatch, {"category": "Dance", "confidence": 0.92})
    r = clf.classify_one("x.jpg")
    assert r["idx"] == oc.LABELS.index("Dance")
    assert abs(r["confidence"] - 0.92) < 1e-9


def test_classify_one_categorie_invalide_va_en_revoir(monkeypatch):
    clf = _clf(monkeypatch, {"category": "Licorne", "confidence": 0.99})
    r = clf.classify_one("x.jpg")
    assert r["confidence"] == 0.0     # < seuil → « À revoir »


def test_classify_one_clamp_confiance(monkeypatch):
    clf = _clf(monkeypatch, {"category": "Family", "confidence": 5})
    assert clf.classify_one("x.jpg")["confidence"] == 1.0


def test_classify_paths_capture_erreurs(monkeypatch):
    monkeypatch.setattr(oc, "_encode_image",
                        lambda p, max_side=None: (_ for _ in ()).throw(ValueError("illisible")))
    clf = oc.OllamaClassifier(); clf.model = "m"
    out = clf.classify_paths(["a.jpg"])
    assert "error" in out[0] and out[0]["path"] == "a.jpg"


def test_batch_repli_clip_quand_ollama_absent(monkeypatch, tmp_path):
    """Ollama indisponible + CLIP absent → no_model, avec message de repli."""
    img = tmp_path / "photo.jpg"
    Image.fromarray(np.zeros((12, 12, 3), np.uint8)).save(str(img))
    monkeypatch.setattr(oc.OllamaClassifier, "load",
                        lambda self: (_ for _ in ()).throw(RuntimeError("serveur éteint")))
    monkeypatch.setattr(C, "assets_available", lambda: False)
    logs = []
    res = C.run_classify_batch(tmp_path, engine="ollama", on_log=logs.append)
    assert res.get("no_model") is True
    assert any("repli" in l.lower() for l in logs)


def test_batch_force_batch_size_1_pour_ollama(monkeypatch, tmp_path):
    """Avec Ollama (per_image), le lot est forcé à 1 (progression fluide)."""
    for i in range(3):
        Image.fromarray(np.zeros((8, 8, 3), np.uint8)).save(str(tmp_path / f"p{i}.jpg"))

    seen = {"max_chunk": 0}

    class FakeOllama:
        per_image = True
        labels = list(oc.LABELS)
        def classify_paths(self, paths):
            seen["max_chunk"] = max(seen["max_chunk"], len(paths))
            return [{"path": str(p), "idx": 0, "confidence": 0.99} for p in paths]

    monkeypatch.setattr(C, "_make_classifier",
                        lambda *a, **k: FakeOllama())
    C.run_classify_batch(tmp_path, engine="ollama", on_log=lambda *_: None)
    assert seen["max_chunk"] == 1


# ── Mode hybride (CLIP + Ollama sur les cas incertains) ───────────────────────

class _FakeClip:
    labels = list(oc.LABELS)
    def __init__(self, results):
        self._results = results
    def classify_paths(self, paths):
        return [dict(r) for r in self._results]


class _FakeOllama:
    labels = list(oc.LABELS)
    def __init__(self, answer):
        self._answer = answer
    def classify_one(self, path):
        return dict(self._answer, path=str(path))


def test_hybrid_garde_clip_si_confiant():
    clip = _FakeClip([{"path": "a.jpg", "idx": 2, "confidence": 0.90}])
    oll = _FakeOllama({"idx": 5, "confidence": 0.99})
    h = C.HybridClassifier(clip, oll, threshold=0.55)
    out = h.classify_paths(["a.jpg"])
    assert out[0]["idx"] == 2            # CLIP gardé (au-dessus du seuil)
    assert "engine" not in out[0]        # le LLM n'a pas été sollicité


def test_hybrid_utilise_ollama_si_incertain():
    clip = _FakeClip([{"path": "a.jpg", "idx": 2, "confidence": 0.30}])
    oll = _FakeOllama({"idx": 5, "confidence": 0.88})
    h = C.HybridClassifier(clip, oll, threshold=0.55)
    out = h.classify_paths(["a.jpg"])
    assert out[0]["idx"] == 5            # avis du LLM adopté
    assert out[0]["confidence"] == 0.88
    assert out[0]["engine"] == "ollama"


def test_hybrid_erreur_ollama_repli_clip():
    class Boom:
        labels = list(oc.LABELS)
        def classify_one(self, p):
            raise RuntimeError("offline")
    clip = _FakeClip([{"path": "a.jpg", "idx": 1, "confidence": 0.10}])
    h = C.HybridClassifier(clip, Boom(), threshold=0.55)
    out = h.classify_paths(["a.jpg"])
    assert out[0]["idx"] == 1            # repli silencieux sur CLIP


def test_make_classifier_hybride_degrade_si_ollama_absent(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(C, "_build_clip", lambda assets_dir, on_log: sentinel)
    monkeypatch.setattr(C, "_build_ollama", lambda *a, **k: None)
    logs = []
    clf = C._make_classifier("hybrid", None, None, None, 300, 0.55, logs.append)
    assert clf is sentinel               # CLIP seul
    assert any("CLIP seul" in l for l in logs)


def test_list_vision_models_filtre(monkeypatch):
    monkeypatch.setattr(oc, "list_models",
                        lambda url=oc.DEFAULT_URL, timeout=5.0: ["gemma4:e2b", "mistral:7b"])
    monkeypatch.setattr(oc, "supports_vision",
                        lambda m, url=oc.DEFAULT_URL, timeout=8.0: "gemma" in m)
    assert oc.list_vision_models() == ["gemma4:e2b"]
