# assets/ — Modèle de classification

Ce dossier doit contenir les 3 produits de `tools/export_clip_assets.py` :

| Fichier | Rôle |
|---------|------|
| `mobileclip_image.onnx` | Encodeur image CLIP exporté en ONNX |
| `text_embeddings.npy` | Matrice `[6, D]` L2-normalisée (1 vecteur par classe) |
| `clip_meta.json` | `{input_size, mean, std, logit_scale, labels[]}` |

Les `.onnx` et `.npy` sont **volumineux** et donc **exclus du dépôt**
(`.gitignore`). Génère-les sur une machine dev :

```bash
pip install -r requirements-dev.txt
python tools/export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k
```

Sans ces fichiers, l'onglet **Classification** affiche un avertissement et
le traitement renvoie « modèle absent » (le reste de l'app fonctionne).
