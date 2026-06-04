"""
make_ico.py — Convertit app_icon.png en app_icon.ico (multi-résolution)
Utilisation : python make_ico.py
Prérequis   : pip install Pillow
"""

from pathlib import Path
from PIL import Image

SRC  = Path(__file__).parent / "app_icon.png"
DEST = Path(__file__).parent / "app_icon.ico"

SIZES = [16, 24, 32, 48, 64, 128, 256]

if not SRC.exists():
    raise FileNotFoundError(
        f"Fichier source introuvable : {SRC}\n"
        "Sauvegarde l'icône sous app_icon.png dans le dossier du projet."
    )

img = Image.open(SRC).convert("RGBA")
icons = [img.resize((s, s), Image.LANCZOS) for s in SIZES]
icons[0].save(str(DEST), format="ICO", sizes=[(s, s) for s in SIZES],
              append_images=icons[1:])
print(f"Icône générée : {DEST}  ({', '.join(str(s) for s in SIZES)} px)")
