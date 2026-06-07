"""
core/ollama_classify.py — Classification via un modèle vision local (Ollama)
============================================================================
Alternative au CLIP zero-shot : un LLM multimodal (ex. qwen3.5) « regarde » la
photo et choisit UNE catégorie du référentiel client, avec une confiance.

Atouts :
- 100 % local (HTTP sur localhost:11434) — aucune donnée ne quitte la machine ;
- aucune dépendance Python ajoutée : urllib (stdlib) + cv2/numpy déjà requis ;
- sortie structurée GARANTIE via le paramètre `format` (schéma JSON) d'Ollama ;
- meilleure compréhension des catégories subjectives (Ambiance, Famille…) que
  la similarité cosinus de CLIP.

Repli : si le serveur est éteint ou aucun modèle vision n'est disponible,
`run_classify_batch` bascule automatiquement sur CLIP (voir core/classification).

`OllamaClassifier` respecte le même contrat que `core.classification.Classifier`
(propriété `labels` + méthode `classify_paths`) pour s'intégrer sans changer la
boucle de traitement.
"""

import base64
import json
import re
import urllib.error
import urllib.request
from typing import List, Optional

import numpy as np

from core.classification import LABELS, CLASSES

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:0.8b"   # léger (peu de RAM/VRAM) ; repli si absent
DEFAULT_TIMEOUT = 120
_MAX_SIDE = 768          # côté max envoyé au modèle (vitesse + taille de payload)

# Indices de nom pour l'auto-sélection d'un modèle multimodal (confirmé ensuite
# par /api/show → capabilities).
_VISION_HINTS = ("qwen", "gemma", "llava", "vision", "-vl", "minicpm-v",
                 "moondream", "bakllava", "pixtral", "qwen2-vl", "qwen2.5vl",
                 "qwen3-vl")


# ── HTTP minimal (stdlib, aucune dépendance) ──────────────────────────────────

def _request(url: str, payload: dict = None, timeout: float = 10.0) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def server_up(url: str = DEFAULT_URL, timeout: float = 4.0) -> bool:
    """True si un serveur Ollama répond sur l'URL donnée."""
    try:
        _request(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def list_models(url: str = DEFAULT_URL, timeout: float = 5.0) -> List[str]:
    """Noms des modèles installés (vide si serveur injoignable)."""
    try:
        d = _request(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return [m.get("name", "") for m in d.get("models", []) if m.get("name")]
    except Exception:
        return []


def supports_vision(model: str, url: str = DEFAULT_URL, timeout: float = 8.0) -> bool:
    """True si le modèle déclare la capacité « vision » (via /api/show)."""
    try:
        d = _request(f"{url.rstrip('/')}/api/show", {"model": model}, timeout=timeout)
        return "vision" in (d.get("capabilities") or [])
    except Exception:
        return False


def list_vision_models(url: str = DEFAULT_URL, timeout: float = 6.0) -> List[str]:
    """Modèles installés qui déclarent la capacité vision (pour le menu de l'UI)."""
    return [m for m in list_models(url, timeout) if supports_vision(m, url, timeout)]


def resolve_model(preferred: str, url: str = DEFAULT_URL,
                  timeout: float = 5.0) -> Optional[str]:
    """Choisit un modèle vision disponible.

    Ordre : le modèle demandé s'il existe et voit ; sinon un modèle de même base
    (sans le tag `:xxx`) ; sinon le premier modèle multimodal détecté. None si
    aucun modèle vision n'est disponible.
    """
    models = list_models(url, timeout)
    if not models:
        return None
    pref = (preferred or "").strip()
    if pref and pref in models and supports_vision(pref, url, timeout):
        return pref
    base = pref.split(":")[0].lower()
    if base:
        for m in models:
            if m.split(":")[0].lower() == base and supports_vision(m, url, timeout):
                return m
    for m in models:
        if any(h in m.lower() for h in _VISION_HINTS) and supports_vision(m, url, timeout):
            return m
    for m in models:                       # dernier recours : tout modèle « vision »
        if supports_vision(m, url, timeout):
            return m
    return None


# ── Prompt + schéma de sortie ─────────────────────────────────────────────────

def build_prompt(labels=LABELS, classes=CLASSES) -> str:
    lines = [
        "You are a professional wedding photo culling assistant.",
        "Look at the photograph and assign it to EXACTLY ONE category below:",
        "",
    ]
    for lab in labels:
        desc = "; ".join(classes.get(lab, []))
        lines.append(f"- {lab}: {desc}.")
    lines += [
        "",
        "Important rules:",
        "- 'Atmosphere' is ONLY for venue/decor/objects with NO people visible.",
        "  If people are clearly present, never choose 'Atmosphere'.",
        "- Choose the single most representative category.",
        "Answer with the category, a confidence between 0 and 1, and a short reason.",
    ]
    return "\n".join(lines)


def output_schema(labels=LABELS) -> dict:
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(labels)},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["category", "confidence"],
    }


def _parse_json(text: str) -> dict:
    """Parse robuste : JSON direct, sinon premier bloc {...} trouvé."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _encode_image(path, max_side: int = _MAX_SIDE) -> str:
    """Décode (chemins non-ASCII OK), réduit, ré-encode JPEG, base64."""
    import cv2
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        raise ValueError(f"image illisible: {path}")
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"image illisible: {path}")
    h, w = img.shape[:2]
    scale = max_side / float(max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise ValueError(f"encodage JPEG impossible: {path}")
    return base64.b64encode(buf.tobytes()).decode("ascii")


# ── Classifieur (même contrat que core.classification.Classifier) ─────────────

class OllamaClassifier:
    per_image = True       # traité une image à la fois → batch_size forcé à 1

    def __init__(self, model: str = None, url: str = None,
                 timeout: float = DEFAULT_TIMEOUT, max_side: int = _MAX_SIDE):
        self.model_pref = model or DEFAULT_MODEL
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.timeout = float(timeout or DEFAULT_TIMEOUT)
        self.max_side = max_side
        self.model = None
        self._labels = list(LABELS)
        self._prompt = build_prompt()
        self._format = output_schema()

    @property
    def labels(self):
        return self._labels

    def load(self) -> None:
        """Vérifie la disponibilité ; lève si serveur éteint / pas de modèle vision."""
        if not server_up(self.url):
            raise RuntimeError(f"serveur Ollama injoignable ({self.url})")
        model = resolve_model(self.model_pref, self.url)
        if not model:
            raise RuntimeError("aucun modèle vision disponible dans Ollama")
        self.model = model

    def _generate(self, b64: str) -> dict:
        payload = {
            "model": self.model,
            "prompt": self._prompt,
            "images": [b64],
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "format": self._format,
        }
        d = _request(f"{self.url}/api/generate", payload, timeout=self.timeout)
        return _parse_json(d.get("response", ""))

    def classify_one(self, path) -> dict:
        b64 = _encode_image(path, self.max_side)
        ans = self._generate(b64)
        cat = ans.get("category", "")
        try:
            conf = float(ans.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        conf = min(max(conf, 0.0), 1.0)
        if cat not in self._labels:
            # hors référentiel → confiance nulle → ira dans « À revoir »
            return {"path": str(path), "idx": 0, "confidence": 0.0}
        return {"path": str(path), "idx": self._labels.index(cat), "confidence": conf}

    def classify_paths(self, paths) -> list:
        out = []
        for p in paths:
            try:
                out.append(self.classify_one(p))
            except Exception as exc:
                out.append({"path": str(p), "error": str(exc)})
        return out
