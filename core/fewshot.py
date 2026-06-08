"""
core/fewshot.py — Classification few-shot par apprentissage des dossiers triés
==============================================================================
Au lieu de DEVINER avec des prompts (zero-shot CLIP) ou un petit LLM lent, on
APPREND la définition réelle de chaque catégorie à partir d'exemples déjà triés
(un sous-dossier = une catégorie).

Pipeline :
    images d'exemple --(embeddings CLIP)--> X[N, D] (L2-normalisés)
    régression logistique multinomiale (numpy, L2) --> tête W[C, D], b[C]
Inférence :
    embed(image) → softmax(W·feat + b) → (catégorie, confiance)

Atouts : rapide (embedding en ms, pas de LLM), 100 % local, aucune dépendance
ajoutée (numpy + l'embedder CLIP onnxruntime déjà présents), et bien plus fiable
sur une taxonomie subjective car il voit TES exemples.

`FewShotClassifier` respecte le contrat de `core.classification.Classifier`
(`labels` + `classify_paths`) pour s'intégrer dans la boucle de traitement.
"""

import re
from pathlib import Path

import numpy as np

from core.classification import (
    Classifier, preprocess, SUPPORTED_EXTENSIONS, LABELS,
)

MODEL_VERSION = 1
_MIN_PER_CLASS = 3
_DEFAULT_MAX_PER_CLASS = 200          # plafond/catégorie (la logreg sature avant)

# Dossiers qui NE sont PAS des catégories visuelles (sélections, sorties…) →
# les inclure polluerait le modèle (ils contiennent des photos de TOUTES classes).
_IGNORE_LABELS = {
    "highlights", "hightlights", "highlight", "best", "best of", "favoris",
    "favorites", "selection", "sélection", "_output", "output", "review",
    "à revoir", "a revoir", "apercu", "aperçu", "export", "exports",
}


def _normalize_label(name: str):
    """« 01 Preparations » → « Preparations ». None si dossier à ignorer.

    Retire un préfixe numérique d'ordre, normalise les espaces, et mappe vers
    les libellés canoniques (insensible à la casse) quand c'est possible.
    """
    s = re.sub(r"^\s*\d+\s*[._)\-]*\s*", "", name)     # « 01 », « 02_ », « 3) »
    s = re.sub(r"\s+", " ", s).strip()
    key = s.lower()
    if not key or key in _IGNORE_LABELS:
        return None
    for lab in LABELS:                                 # canonicalise si match
        if lab.lower() == key:
            return lab
    return s


def default_model_path() -> Path:
    from core.config import config_dir
    return config_dir() / "fewshot_model.npz"


def _l2(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


# ── Embeddings ────────────────────────────────────────────────────────────────

def _embed_blobs(embedder: Classifier, blobs) -> np.ndarray:
    """Forward CLIP sur une pile de blobs [n,3,H,W] → embeddings L2 [n,D]."""
    feats = embedder.forward(np.concatenate(blobs, axis=0))
    return _l2(np.asarray(feats, np.float32))


def _embed_paths(embedder: Classifier, paths, batch: int = 16,
                 on_each=None) -> tuple:
    """Embeddings des chemins valides. Retourne (X[n,D], chemins_ok)."""
    feats, ok = [], []
    for s in range(0, len(paths), batch):
        chunk = paths[s:s + batch]
        blobs, valid = [], []
        for p in chunk:
            try:
                blobs.append(preprocess(p, embedder.input_size,
                                        embedder.mean, embedder.std))
                valid.append(p)
            except Exception:
                pass
            if on_each:
                on_each()
        if blobs:
            X = _embed_blobs(embedder, blobs)
            feats.extend(X)
            ok.extend(valid)
    if not feats:
        return np.zeros((0, 0), np.float32), []
    return np.asarray(feats, np.float32), ok


# ── Entraînement (régression logistique multinomiale, numpy) ──────────────────

def _train_logreg(X: np.ndarray, y: np.ndarray, n_classes: int,
                  epochs: int = 400, lr: float = 0.5, reg: float = 1e-3):
    """Régression logistique softmax L2-régularisée par descente de gradient."""
    n, d = X.shape
    W = np.zeros((n_classes, d), np.float32)
    b = np.zeros(n_classes, np.float32)
    Y = np.eye(n_classes, dtype=np.float32)[y]
    for _ in range(epochs):
        logits = X @ W.T + b
        logits -= logits.max(axis=1, keepdims=True)
        e = np.exp(logits)
        P = e / e.sum(axis=1, keepdims=True)
        G = (P - Y) / n
        W -= lr * (G.T @ X + reg * W)
        b -= lr * G.sum(axis=0)
    return W, b


def _predict(X, W, b):
    logits = X @ W.T + b
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def _gather_examples(train_dirs, on_log, max_per_class=_DEFAULT_MAX_PER_CLASS):
    """{catégorie: [chemins]} fusionné sur 1..N dossiers d'apprentissage.

    Noms normalisés (« 01 Preparations »→« Preparations »), dossiers non-catégorie
    ignorés, et chaque classe plafonnée à `max_per_class` (échantillon aléatoire).
    """
    if isinstance(train_dirs, (str, Path)):
        train_dirs = [train_dirs]

    buckets = {}                                       # label normalisé → [chemins]
    for root in train_dirs:
        root = Path(root)
        if not root.exists():
            on_log(f"  ⚠ dossier introuvable : {root}")
            continue
        for d in sorted(x for x in root.iterdir()
                        if x.is_dir() and not x.name.startswith(".")):
            label = _normalize_label(d.name)
            if label is None:
                on_log(f"  ⊘ « {d.name} » ignoré (sélection / non-catégorie)")
                continue
            imgs = [p for p in d.rglob("*")
                    if p.suffix in SUPPORTED_EXTENSIONS and not p.name.startswith("._")]
            buckets.setdefault(label, []).extend(imgs)

    rng = np.random.default_rng(0)
    per_class = {}
    for label, imgs in buckets.items():
        if len(imgs) < _MIN_PER_CLASS:
            on_log(f"  ⚠ « {label} » ignoré ({len(imgs)} image(s) < {_MIN_PER_CLASS}).")
            continue
        kept = imgs
        if max_per_class and len(imgs) > max_per_class:
            idx = sorted(rng.choice(len(imgs), size=max_per_class, replace=False))
            kept = [imgs[i] for i in idx]
            on_log(f"  • {label} : {len(imgs)} → {max_per_class} (échantillon)")
        per_class[label] = kept
    return per_class


class CancelledError(Exception):
    """Levée quand l'entraînement est annulé par l'utilisateur."""


def train_from_folders(train_dirs, embedder: Classifier,
                       on_log=print, on_progress=None, cancel_event=None,
                       max_per_class=_DEFAULT_MAX_PER_CLASS) -> dict:
    """Entraîne la tête few-shot depuis 1..N dossiers (sous-dossiers = catégories).

    `train_dirs` : un chemin ou une liste de chemins (mariages déjà triés). Les
    noms sont normalisés et fusionnés ; chaque classe est plafonnée à
    `max_per_class`. Retourne {"labels","W","b","n","acc"} (acc = validation 15 %).
    Lève RuntimeError si < 2 catégories exploitables, CancelledError si annulé.
    """
    per_class = _gather_examples(train_dirs, on_log, max_per_class)
    if len(per_class) < 2:
        raise RuntimeError("au moins 2 catégories avec ≥ "
                           f"{_MIN_PER_CLASS} images sont requises")

    labels = list(per_class.keys())
    total = sum(len(v) for v in per_class.values())
    on_log(f"  {total} exemples · {len(labels)} catégories : "
           + ", ".join(labels))

    done = [0]

    def tick():
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()
        done[0] += 1
        if on_progress:
            on_progress(done[0], total)

    X_list, y_list = [], []
    for ci, lab in enumerate(labels):
        emb, ok = _embed_paths(embedder, per_class[lab], on_each=tick)
        if len(ok):
            X_list.append(emb)
            y_list.extend([ci] * len(ok))
            on_log(f"    • {lab} : {len(ok)} encodé(s)")
    X = np.concatenate(X_list, axis=0).astype(np.float32)
    y = np.asarray(y_list, np.int64)

    # split 85/15 pour une précision honnête, puis ré-entraînement sur tout
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]
    n_val = max(len(y) // 7, len(labels))
    if len(y) - n_val >= len(labels) * _MIN_PER_CLASS:
        Wv, bv = _train_logreg(X[n_val:], y[n_val:], len(labels))
        acc = float((_predict(X[:n_val], Wv, bv).argmax(1) == y[:n_val]).mean())
    else:
        acc = float("nan")

    W, b = _train_logreg(X, y, len(labels))           # modèle final sur tout
    if acc == acc:                                    # not NaN
        on_log(f"  Précision (validation) : {acc:.0%}")
    return {"labels": labels, "W": W, "b": b, "n": int(len(y)), "acc": acc}


# ── Persistance ───────────────────────────────────────────────────────────────

def save_model(result: dict, path=None) -> Path:
    path = Path(path or default_model_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(str(path),
             version=np.int64(MODEL_VERSION),
             labels=np.asarray(result["labels"]),
             W=result["W"].astype(np.float32),
             b=result["b"].astype(np.float32),
             n=np.int64(result.get("n", 0)),
             acc=np.float32(result.get("acc", float("nan"))))
    return path


def load_model(path=None):
    path = Path(path or default_model_path())
    if not path.exists():
        return None
    try:
        d = np.load(str(path), allow_pickle=False)
        return {
            "labels": [str(x) for x in d["labels"].tolist()],
            "W": d["W"].astype(np.float32),
            "b": d["b"].astype(np.float32),
            "n": int(d["n"]),
            "acc": float(d["acc"]),
        }
    except Exception:
        return None


def model_info(path=None):
    """Résumé léger du modèle entraîné (ou None)."""
    m = load_model(path)
    if not m:
        return None
    return {"labels": m["labels"], "n": m["n"], "acc": m["acc"]}


# ── Classifieur (même contrat que Classifier) ─────────────────────────────────

class FewShotClassifier:
    per_image = False

    def __init__(self, embedder: Classifier, labels, W, b):
        self.embedder = embedder
        self._labels = list(labels)
        self.W = np.asarray(W, np.float32)
        self.b = np.asarray(b, np.float32)

    @property
    def labels(self):
        return self._labels

    @classmethod
    def from_model(cls, embedder: Classifier, model: dict):
        return cls(embedder, model["labels"], model["W"], model["b"])

    def classify_paths(self, paths):
        results = [None] * len(paths)
        blobs, idxs = [], []
        for i, p in enumerate(paths):
            try:
                blobs.append(preprocess(p, self.embedder.input_size,
                                        self.embedder.mean, self.embedder.std))
                idxs.append(i)
            except Exception as exc:
                results[i] = {"path": str(p), "error": str(exc)}
        if blobs:
            X = _embed_blobs(self.embedder, blobs)
            P = _predict(X, self.W, self.b)
            for i, probs in zip(idxs, P):
                k = int(probs.argmax())
                results[i] = {"path": str(paths[i]), "idx": k,
                              "confidence": float(probs[k])}
        return results
