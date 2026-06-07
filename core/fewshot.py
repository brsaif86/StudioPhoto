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

from pathlib import Path

import numpy as np

from core.classification import (
    Classifier, preprocess, SUPPORTED_EXTENSIONS,
)

MODEL_VERSION = 1
_MIN_PER_CLASS = 3


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


def _gather_examples(train_dir: Path, on_log):
    """{catégorie: [chemins]} pour chaque sous-dossier ayant assez d'exemples."""
    train_dir = Path(train_dir)
    per_class = {}
    subdirs = [d for d in sorted(train_dir.iterdir())
               if d.is_dir() and not d.name.startswith((".", "_"))]
    for d in subdirs:
        imgs = sorted(p for p in d.rglob("*")
                      if p.suffix in SUPPORTED_EXTENSIONS
                      and not p.name.startswith("._"))
        if len(imgs) >= _MIN_PER_CLASS:
            per_class[d.name] = imgs
        elif imgs:
            on_log(f"  ⚠ « {d.name} » ignoré ({len(imgs)} image(s) < {_MIN_PER_CLASS}).")
    return per_class


class CancelledError(Exception):
    """Levée quand l'entraînement est annulé par l'utilisateur."""


def train_from_folders(train_dir, embedder: Classifier,
                       on_log=print, on_progress=None, cancel_event=None) -> dict:
    """Entraîne la tête few-shot depuis des sous-dossiers (un par catégorie).

    Retourne {"labels", "W", "b", "n", "acc"} (acc = précision sur 15 % retenus).
    Lève RuntimeError si moins de 2 catégories exploitables, CancelledError si
    `cancel_event` est déclenché en cours de route.
    """
    per_class = _gather_examples(train_dir, on_log)
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
