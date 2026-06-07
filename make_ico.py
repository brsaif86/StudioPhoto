"""
make_ico.py — Convertit app_icon.png en app_icon.ico (multi-résolution, carré)
==============================================================================
- Recadre sur le contenu réel (supprime les marges transparentes)
- Rend l'image parfaitement carrée (padding centré, sans déformation)
- Génère un ICO multi-résolution propre (16 → 256 px)

Utilisation : python make_ico.py
Prérequis   : pip install Pillow
"""

from pathlib import Path
from PIL import Image

SRC  = Path(__file__).parent / "app_icon.png"
DEST = Path(__file__).parent / "app_icon.ico"

SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_square(img: Image.Image) -> Image.Image:
    """Recadre sur le contenu non transparent puis pad en carré centré."""
    img = img.convert("RGBA")

    # 1. Recadre sur le contenu réel (bbox du canal alpha)
    bbox = img.getbbox()                     # ignore les bords transparents
    if bbox:
        img = img.crop(bbox)

    # 2. Pad en carré (côté = max largeur/hauteur), contenu centré
    w, h = img.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return square


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(
            f"Fichier source introuvable : {SRC}\n"
            "Sauvegarde l'icône sous app_icon.png dans le dossier du projet."
        )

    base = make_square(Image.open(SRC))
    print(f"Source : {Image.open(SRC).size}  ->  carre : {base.size}")

    # Rééchantillonne chaque taille depuis le carré (pas de déformation)
    base.save(
        str(DEST),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )

    # Sauve aussi un PNG carré propre (utile pour l'icône Qt et macOS)
    square_png = SRC.with_name("app_icon_square.png")
    base.resize((512, 512), Image.LANCZOS).save(str(square_png))

    print(f"Icone generee : {DEST}  ({', '.join(str(s) for s in SIZES)} px)")
    print(f"PNG carre     : {square_png}  (512x512)")


if __name__ == "__main__":
    main()
