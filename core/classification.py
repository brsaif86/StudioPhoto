"""
core/classification.py — Tri auto zero-shot (CLIP/MobileCLIP via OpenCV)
========================================================================
Moteur PUR, sans dépendance UI. Inférence mono-process, modèle ONNX chargé
une fois, embeddings texte précalculés (.npy). Aucune dépendance torch au
runtime — uniquement cv2 + numpy.

Pipeline :
    image --(cv2 preprocess)--> blob --(cv2.dnn ONNX)--> feature [D]
    feature · text_emb.T * logit_scale --softmax--> probabilités par classe
    argmax → catégorie ; si conf < seuil → « À revoir »
"""

import csv
import json
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

# ── Constantes ────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"}
REVIEW_LABEL = "À revoir"
DEFAULT_THRESHOLD = 0.45

TEMPLATES = [
    "a photo of {}",
    "a wedding photograph showing {}",
    "{} at a wedding",
]

# L'ORDRE des clés EST le mapping index → catégorie (affichée telle quelle).
CLASSES = {
    "Preparations": [
        "the bride or groom getting ready",
        "makeup, hair and dressing before the ceremony",
        "wedding dress, suit, rings and shoes laid out",
    ],
    "Love Story": [
        "the couple together in a romantic portrait",
        "bride and groom kissing or embracing",
        "the first look between the couple",
    ],
    "Atmosphere": [
        "an empty wedding venue without people",
        "the decorated ceremony canopy and chairs with nobody present",
        "close-up of flowers, candles, table settings and decor details",
    ],
    "Family": [
        "a family group portrait at a wedding",
        "parents, grandparents and relatives posing together",
    ],
    "Ktuba and Huppa": [
        "a Jewish wedding ceremony under the chuppah canopy",
        "the ketubah signing with a rabbi",
        "a couple standing under a wedding canopy during a religious ritual",
    ],
    "Dance": [
        "guests dancing at the wedding reception",
        "a hora dance and party on the dance floor",
        "celebration with music and movement",
    ],
}

LABELS = list(CLASSES.keys())   # ordre canonique


# ── Localisation des assets (compatible PyInstaller --onefile) ────────────────

def _assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets"


def assets_available() -> bool:
    d = _assets_dir()
    return (
        (d / "mobileclip_image.onnx").exists()
        and (d / "text_embeddings.npy").exists()
        and (d / "clip_meta.json").exists()
    )


# ── Prétraitement (OpenCV) ────────────────────────────────────────────────────

def preprocess(path, size: int, mean, std) -> np.ndarray:
    """Décode + redimensionne + normalise une image en blob NCHW float32 [1,3,H,W].

    Lecture via np.fromfile + cv2.imdecode : cv2.imread échoue sur les chemins
    non-ASCII (accents, hébreu…) sous Windows.
    """
    import cv2
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        raise ValueError(f"image illisible: {path}")
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)           # BGR uint8
    if img is None:
        raise ValueError(f"image illisible: {path}")
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img = (img - np.asarray(mean, np.float32)) / np.asarray(std, np.float32)
    return np.transpose(img, (2, 0, 1))[None]            # [1,3,H,W]


# ── Confiance calibrée (pur numpy, testable) ──────────────────────────────────

def softmax_confidence(feat: np.ndarray, text_emb: np.ndarray, logit_scale: float):
    """feat [N,D] (non normalisé) → (indices [N], confiances [N], probs [N,C]).

    text_emb [C,D] doit être L2-normalisé. logit_scale ≈ 100 (valeur apprise).
    """
    feat = np.atleast_2d(feat).astype(np.float32)
    feat = feat / (np.linalg.norm(feat, axis=1, keepdims=True) + 1e-8)
    logits = logit_scale * (feat @ text_emb.T)
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = e / e.sum(axis=1, keepdims=True)
    idx = probs.argmax(axis=1)
    conf = probs[np.arange(len(idx)), idx]
    return idx, conf, probs


def category_for(idx: int, conf: float, threshold: float, labels=LABELS) -> str:
    """Mappe (index, confiance) → nom de catégorie, ou « À revoir » sous le seuil."""
    if conf < threshold:
        return REVIEW_LABEL
    return labels[idx]


# ── Classifieur (charge le modèle une fois) ───────────────────────────────────

class Classifier:
    """Encapsule le réseau ONNX + embeddings texte + métadonnées."""

    def __init__(self, assets_dir: Path = None):
        self._dir = Path(assets_dir) if assets_dir else _assets_dir()
        self._net = None
        self._sess = None
        self._backend = None
        self._in_name = None
        self._text_emb = None
        self._meta = None

    def load(self) -> None:
        meta_path = self._dir / "clip_meta.json"
        self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self._text_emb = np.load(self._dir / "text_embeddings.npy").astype(np.float32)
        # garantir la normalisation L2 des embeddings texte
        self._text_emb /= (np.linalg.norm(self._text_emb, axis=1, keepdims=True) + 1e-8)

        onnx_path = str(self._dir / "mobileclip_image.onnx")
        # Backend d'inférence : onnxruntime (CPU, supporte les ViT) en priorité,
        # cv2.dnn en repli. Aucun des deux n'embarque torch.
        try:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = 0   # auto (tous les cœurs)
            self._sess = ort.InferenceSession(onnx_path, sess_options=so,
                                              providers=["CPUExecutionProvider"])
            self._in_name = self._sess.get_inputs()[0].name
            self._backend = "ort"
        except ImportError:
            import cv2
            self._net = cv2.dnn.readNetFromONNX(onnx_path)
            self._backend = "cv2"

    # — accès métadonnées —
    @property
    def input_size(self) -> int:
        return int(self._meta["input_size"])

    @property
    def mean(self):
        return self._meta["mean"]

    @property
    def std(self):
        return self._meta["std"]

    @property
    def logit_scale(self) -> float:
        return float(self._meta["logit_scale"])

    @property
    def labels(self):
        return self._meta.get("labels", LABELS)

    def forward(self, blob: np.ndarray) -> np.ndarray:
        """Inférence sur un blob [B,3,H,W] → features [B,D]."""
        if getattr(self, "_backend", "cv2") == "ort":
            return self._sess.run(None, {self._in_name: blob.astype(np.float32)})[0]
        self._net.setInput(blob)
        return self._net.forward()

    def classify_paths(self, paths):
        """Classe une liste de chemins (batch). Retourne liste de dicts/erreurs.

        Chaque entrée : {"path", "category", "confidence"} ou {"path", "error"}.
        """
        blobs, valid = [], []
        results = []
        for p in paths:
            try:
                blobs.append(preprocess(p, self.input_size, self.mean, self.std))
                valid.append(p)
            except Exception as exc:
                results.append({"path": str(p), "error": str(exc)})
        if not valid:
            return results

        batch = np.concatenate(blobs, axis=0)
        feats = self.forward(batch)
        idx, conf, _ = softmax_confidence(feats, self._text_emb, self.logit_scale)
        for p, i, c in zip(valid, idx, conf):
            results.append({"path": str(p), "idx": int(i), "confidence": float(c)})
        return results


# ── Collecte des fichiers ─────────────────────────────────────────────────────

def collect_images(folder: Path, recursive: bool) -> list:
    candidates = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        p for p in candidates
        if p.suffix in SUPPORTED_EXTENSIONS
        and not p.name.startswith("._")
        and not any(seg in {c for c in LABELS} | {REVIEW_LABEL, "_output"} for seg in p.parts)
    )


# ── Écriture du manifest ──────────────────────────────────────────────────────

def write_manifest(rows: list, out_path: Path) -> None:
    """Écrit results.json ou results.csv, trié par confiance décroissante."""
    rows = sorted(rows, key=lambda r: r.get("confidence", -1.0), reverse=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".csv":
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["path", "category", "confidence"])
            for r in rows:
                w.writerow([r["path"], r.get("category", ""), f"{r.get('confidence', 0):.4f}"])
    else:
        out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Tri physique ──────────────────────────────────────────────────────────────

def _place(src: Path, dest_dir: Path, mode: str) -> None:
    import shutil
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        dest = dest_dir / f"{src.stem}_{int(time.time()*1000)%100000}{src.suffix}"
    if mode == "move":
        shutil.move(str(src), str(dest))
    else:  # copy
        shutil.copy2(str(src), str(dest))


# ── Pipeline batch avec callbacks (réutilise la progress card) ────────────────

def run_classify_batch(
    folder: Path,
    output_dir=None,
    mode: str = "manifest",          # "manifest" | "copy" | "move"
    threshold: float = DEFAULT_THRESHOLD,
    recursive: bool = True,
    batch_size: int = 16,
    manifest_name: str = "results.json",
    assets_dir: Path = None,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = None,
    on_current: Callable[[str, str], None] = None,
    on_speed: Callable[[float], None] = None,
    on_eta: Callable[[int], None] = None,
    cancel_event: threading.Event = None,
) -> dict:
    """Classe toutes les images d'un dossier. Mono-process, inférence batchée."""
    folder = Path(folder)
    if not assets_available() and assets_dir is None:
        on_log("  ✗ Modèle absent : place mobileclip_image.onnx, text_embeddings.npy "
               "et clip_meta.json dans assets/ (voir tools/export_clip_assets.py).")
        return {"ok": 0, "review": 0, "errors": 0, "total": 0, "no_model": True}

    files = collect_images(folder, recursive)
    total = len(files)
    if total == 0:
        on_log("  Aucune image trouvée.")
        return {"ok": 0, "review": 0, "errors": 0, "total": 0}

    clf = Classifier(assets_dir)
    try:
        clf.load()
    except Exception as exc:
        on_log(f"  ✗ Échec chargement modèle : {exc}")
        return {"ok": 0, "review": 0, "errors": 0, "total": total, "no_model": True}

    out_base = Path(output_dir) if output_dir else folder
    rows, ok = [], 0
    review = err = 0
    done = 0
    t0 = time.perf_counter()
    _times: list[float] = []

    for start in range(0, total, batch_size):
        if cancel_event and cancel_event.is_set():
            break
        chunk = files[start:start + batch_size]
        try:
            res = clf.classify_paths(chunk)
        except Exception as exc:
            # échec batch entier → on logge et continue
            for p in chunk:
                on_log(f"  ✗ ERREUR {Path(p).name}: {exc}")
                err += 1
                done += 1
            if on_progress:
                on_progress(done, total)
            continue

        for r in res:
            done += 1
            p = Path(r["path"])
            if "error" in r:
                on_log(f"  ✗ ERREUR {p.name}: {r['error']}")
                err += 1
            else:
                cat = category_for(r["idx"], r["confidence"], threshold, clf.labels)
                r["category"] = cat
                rows.append({"path": r["path"], "category": cat,
                             "confidence": r["confidence"]})
                if cat == REVIEW_LABEL:
                    review += 1
                    on_log(f"  ⏭ [À revoir] {p.name}  ({r['confidence']:.0%})")
                else:
                    ok += 1
                    on_log(f"  ✓ [{cat}] {p.name}  ({r['confidence']:.0%})")
                if mode in ("copy", "move"):
                    try:
                        _place(p, out_base / cat, mode)
                    except Exception as exc:
                        on_log(f"    ⚠ tri impossible ({exc})")

            # progression / vitesse / ETA
            elapsed = time.perf_counter() - t0
            _times.append(elapsed)
            if len(_times) > 20:
                _times.pop(0)
            speed = ((len(_times) - 1) / (_times[-1] - _times[0])
                     if len(_times) >= 2 and _times[-1] > _times[0] else
                     done / elapsed if elapsed > 0 else 0)
            if on_current:
                on_current(p.parent.name, p.name)
            if on_speed:
                on_speed(speed)
            if on_eta and speed > 0:
                on_eta(int((total - done) / speed))
            if on_progress:
                on_progress(done, total)

    if mode == "manifest" and rows:
        manifest_path = out_base / manifest_name
        write_manifest(rows, manifest_path)
        on_log(f"  → Manifest : {manifest_path}")

    return {"ok": ok, "review": review, "errors": err, "total": total,
            "cancelled": bool(cancel_event and cancel_event.is_set())}
