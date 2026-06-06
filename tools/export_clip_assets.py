"""
tools/export_clip_assets.py — Export HORS-LIGNE des assets CLIP/MobileCLIP
==========================================================================
À exécuter UNE FOIS sur une machine dev (torch requis — voir requirements-dev.txt).
N'est PAS packagé dans l'.exe : seuls ses 3 produits le sont.

Produit dans assets/ :
    mobileclip_image.onnx   encodeur image (ONNX, batch dynamique)
    text_embeddings.npy     matrice [6, D] L2-normalisée (1 vecteur par classe)
    clip_meta.json          {input_size, mean, std, logit_scale, labels[]}

Usage :
    python tools/export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k
    python tools/export_clip_assets.py --model mobileclip_s0 --pretrained datacompdr

Le code supporte deux backends :
  - open_clip (par défaut, large couverture de modèles)
  - mobileclip (package Apple) si --backend mobileclip
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


def export_open_clip(model_name: str, pretrained: str):
    import torch
    import open_clip

    model, _, _ = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()

    # — taille d'entrée + normalisation —
    cfg = model.visual.image_size if hasattr(model.visual, "image_size") else 224
    input_size = cfg[0] if isinstance(cfg, (tuple, list)) else int(cfg)
    # normalisation CLIP standard
    mean = [0.48145466, 0.4578275, 0.40821073]
    std  = [0.26862954, 0.26130258, 0.27577711]
    logit_scale = float(model.logit_scale.exp().detach().cpu().numpy())

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
    torch.onnx.export(
        enc, dummy, str(onnx_path),
        input_names=["image"], output_names=["features"],
        dynamic_axes={"image": {0: "batch"}, "features": {0: "batch"}},
        opset_version=14,
    )

    np.save(ASSETS / "text_embeddings.npy", text_emb)
    meta = {
        "input_size": input_size,
        "mean": mean, "std": std,
        "logit_scale": logit_scale,
        "labels": LABELS,
        "model": f"{model_name}/{pretrained}",
        "dim": int(text_emb.shape[1]),
    }
    (ASSETS / "clip_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"OK — assets écrits dans {ASSETS}")
    print(f"  input_size={input_size}  dim={text_emb.shape[1]}  logit_scale={logit_scale:.2f}")


def main():
    ap = argparse.ArgumentParser(description="Export CLIP assets (offline)")
    ap.add_argument("--backend", choices=["open_clip"], default="open_clip")
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="laion2b_s34b_b79k")
    args = ap.parse_args()
    export_open_clip(args.model, args.pretrained)


if __name__ == "__main__":
    main()
