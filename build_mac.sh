#!/usr/bin/env bash
# build_mac.sh — Build StudioPhoto sur macOS (Intel ou Apple Silicon)
# Produit un binaire natif de l'architecture de la machine qui exécute ce script.
#
# Usage :
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Pré-requis : Python 3.11+ (brew install python@3.11)

set -e
cd "$(dirname "$0")"

echo "==> Architecture : $(uname -m)   (arm64 = Apple Silicon, x86_64 = Intel)"

# 1. Environnement virtuel
if [ ! -d ".venv" ]; then
    echo "==> Création de l'environnement virtuel…"
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Dépendances runtime (sans torch)
echo "==> Installation des dépendances…"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# 3. Vérification du modèle de classification (optionnel)
if [ -f assets/mobileclip_image.onnx ] && [ -f assets/text_embeddings.npy ] && [ -f assets/clip_meta.json ]; then
    echo "==> Modèle de classification présent → build avec tri auto."
else
    echo "==> Modèle de classification absent (assets/)."
    echo "    L'app marchera sans le tri auto. Pour l'activer :"
    echo "      - copie le dossier assets/ depuis une autre machine, OU"
    echo "      - pip install -r requirements-dev.txt && \\"
    echo "        python tools/export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k"
fi

# 4. Tests rapides
echo "==> Tests…"
python -m pytest tests/ -q

# 5. Build
echo "==> Build PyInstaller…"
python build.py

echo ""
echo "==> Terminé. Voir le dossier dist/."
echo "    Lancement : ouvre dist/StudioPhoto-<version>/StudioPhoto-<version>"
echo "    1er lancement bloqué par Gatekeeper ? :"
echo "      xattr -dr com.apple.quarantine dist/StudioPhoto-*"
