"""
tools/export_clip_assets.py — Export HORS-LIGNE des assets CLIP/MobileCLIP
==========================================================================
À exécuter UNE FOIS sur une machine dev (torch requis — voir requirements-dev.txt).
N'est PAS packagé dans l'.exe : seuls ses 3 produits le sont.

Produit dans assets/ :
    mobileclip_image.onnx   encodeur image (ONNX, batch dynamique)
    text_embeddings.npy     matrice [6, D] L2-normalisée (1 vecteur par classe)
    clip_meta.json          {input_size, mean, std, logit_scale, labels[]}

Usage (SigLIP recommandé — meilleurs embeddings pour le few-shot) :
    python tools/export_clip_assets.py --model ViT-B-16-SigLIP-256 --pretrained webli
    python tools/export_clip_assets.py --model ViT-L-16-SigLIP-256  --pretrained webli
    # ancien backbone CLIP (plus rapide, moins précis) :
    python tools/export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k

La normalisation (mean/std) est lue automatiquement sur le modèle — SigLIP
utilise [0.5,0.5,0.5], CLIP des valeurs différentes : ne pas hardcoder.
"""

import argparse
import json
from pathlib import Path

import numpy as np

# Import partagé avec le moteur runtime pour garantir le MÊME mapping/prompts
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.classification import CLASSES, TEMPLATES, LABELS   # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def build_text_prompts():
    """Retourne {classe: [phrases templatisées]}."""
    out = {}
    for cls, descs in CLASSES.items():
        phrases = []
        for d in descs:
            for t in TEMPLATES:
                phrases.append(t.format(d))
        out[cls] = phrases
    return out


def _norm_from_transform(preprocess):
    """Lit (mean, std) depuis la transform de validation open_clip.

    CRITIQUE : SigLIP normalise en [0.5,0.5,0.5] (≠ CLIP). On lit la VRAIE
    normalisation du modèle au lieu de la hardcoder, sinon les embeddings sont
    corrompus.
    """
    try:
        from torchvision.transforms import Normalize
        for t in getattr(preprocess, "transforms", []):
            if isinstance(t, Normalize):
                return [float(x) for x in t.mean], [float(x) for x in t.std]
    except Exception:
        pass
    return None


def export_open_clip(model_name: str, pretrained: str):
    import torch
    import open_clip

    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name, pretrained=pretrained)
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()

    is_siglip = "siglip" in model_name.lower()

    # — taille d'entrée + normalisation RÉELLES du modèle —
    cfg = model.visual.image_size if hasattr(model.visual, "image_size") else 224
    input_size = cfg[0] if isinstance(cfg, (tuple, list)) else int(cfg)
    norm = _norm_from_transform(preprocess)
    if norm:
        mean, std = norm
    else:                                    # repli normalisation CLIP standard
        mean = [0.48145466, 0.4578275, 0.40821073]
        std  = [0.26862954, 0.26130258, 0.27577711]
    logit_scale = float(model.logit_scale.exp().detach().cpu().numpy())
    # SigLIP : score sigmoïde avec biais (info pour le zero-shot ; le few-shot
    # n'utilise que les embeddings image et s'en moque).
    logit_bias = None
    if getattr(model, "logit_bias", None) is not None:
        logit_bias = float(model.logit_bias.detach().cpu().numpy())

    # — embeddings texte : encode, L2, moyenne par classe, re-L2 —
    prompts = build_text_prompts()
    class_vecs = []
    with torch.no_grad():
        for cls in LABELS:
            toks = tokenizer(prompts[cls])
            t = model.encode_text(toks)
            t = t / t.norm(dim=-1, keepdim=True)
            v = t.mean(dim=0)
            v = v / v.norm()
            class_vecs.append(v.cpu().numpy().astype(np.float32))
    text_emb = np.stack(class_vecs, axis=0)                 # [6, D]

    # Centrage : on retire 50 % de la composante commune à toutes les classes
    # (direction « générique » qui sur-attire certaines classes), puis re-L2.
    # Améliore la séparation des classes visuellement proches.
    text_emb = text_emb - 0.5 * text_emb.mean(axis=0, keepdims=True)
    text_emb = text_emb / (np.linalg.norm(text_emb, axis=1, keepdims=True) + 1e-8)

    # — export ONNX de l'encodeur image —
    class ImageEncoder(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m
        def forward(self, x):
            f = self.m.encode_image(x)
            return f / f.norm(dim=-1, keepdim=True)

    enc = ImageEncoder(model).eval()
    dummy = torch.randn(1, 3, input_size, input_size)
    ASSETS.mkdir(parents=True, exist_ok=True)
    onnx_path = ASSETS / "mobileclip_image.onnx"
    # dynamo=False → exporteur TorchScript legacy : opset 14, poids embarqués,
    # ONNX lisible par cv2.dnn (le nouvel exporteur dynamo produit des opsets
    # récents non supportés par OpenCV).
    torch.onnx.export(
        enc, dummy, str(onnx_path),
        input_names=["image"], output_names=["features"],
        dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}},
        opset_version=14,
        dynamo=False,
    )

    np.save(ASSETS / "text_embeddings.npy", text_emb)
    meta = {
        "input_size": input_size,
        "mean": mean, "std": std,
        "logit_scale": logit_scale,
        "labels": LABELS,
        "model": f"{model_name}/{pretrained}",
        "dim": int(text_emb.shape[1]),
        "scoring": "sigmoid" if is_siglip else "softmax",
    }
    if logit_bias is not None:
        meta["logit_bias"] = logit_bias
    (ASSETS / "clip_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"OK — assets écrits dans {ASSETS}")
    print(f"  modèle={model_name}/{pretrained}  ({'SigLIP' if is_siglip else 'CLIP'})")
    print(f"  input_size={input_size}  dim={text_emb.shape[1]}  "
          f"mean={[round(x,3) for x in mean]}  logit_scale={logit_scale:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Export CLIP assets (offline)")
    ap.add_argument("--backend", choices=["open_clip"], default="open_clip")
    ap.add_argument("--model", default="ViT-B-16-SigLIP-256")
    ap.add_argument("--pretrained", default="webli")
    args = ap.parse_args()
    export_open_clip(args.model, args.pretrained)


if __name__ == "__main__":
    main()
