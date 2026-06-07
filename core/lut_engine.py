"""
core/lut_engine.py — Moteur de LUT 3D et Vibrance
=================================================
Gestion du chargement de fichiers .cube et application par interpolation trilinéaire.
"""

import sys
import numpy as np
import cv2
from pathlib import Path
from functools import lru_cache
from typing import List, Tuple, Optional


def default_lut_dir() -> Path:
    """Dossier des LUT livrées, résolu en dev comme en .exe (PyInstaller).

    En exe figé, les assets sont extraits dans sys._MEIPASS ; en dev on
    pointe sur le dossier assets/ du dépôt.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "luts"


def load_cube_lut(path) -> Tuple[np.ndarray, int]:
    """
    Lit un fichier .cube standard (str ou Path accepté).
    Retourne (lut_array indexé [R, G, B] → (r,g,b), size).
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    size = 0
    data = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("LUT_3D_SIZE"):
            # Format: LUT_3D_SIZE 33
            parts = line.split()
            if len(parts) >= 2:
                size = int(parts[1])
            continue

        # On suppose que les valeurs sont des flottants (R G B)
        try:
            coords = [float(x) for x in line.split()]
            if len(coords) == 3:
                data.append(coords)
        except ValueError:
            continue

    if not data:
        raise ValueError(f"Aucune donnée de couleur trouvée dans le fichier {path}")

    arr = np.array(data, dtype=np.float32)

    # Si le fichier n'indiquait pas la taille explicitement, on la déduit
    if size == 0:
        size = int(round(len(data)**(1/3)))

    # Dans un .cube, le ROUGE varie le plus vite : l'ordre des lignes est
    # (r=0,g=0,b=0), (r=1,g=0,b=0), … Le reshape NumPy (ordre C) donne donc un
    # tableau indexé [B, G, R]. On transpose en [R, G, B] pour que apply_lut
    # puisse indexer directement lut[r, g, b] = couleur (r, g, b).
    lut = arr.reshape((size, size, size, 3)).transpose(2, 1, 0, 3).copy()

    return lut, size


# ── Cache module-level (partagé entre instances ET images d'un même process) ──

@lru_cache(maxsize=16)
def _load_lut_cached(lut_dir: str, lut_name: str) -> Tuple[np.ndarray, int]:
    """Charge (une seule fois) une LUT identifiée par (dossier, nom)."""
    return load_cube_lut(Path(lut_dir) / lut_name)


def apply_lut(img_float: np.ndarray, lut: np.ndarray, size: int) -> np.ndarray:
    """
    Applique la LUT par interpolation trilinéaire sur une image float32 [0-1] RGB.
    Implémentation NumPy vectorisée pour la performance.
    """
    # img_float shape: (H, W, 3)
    # lut shape: (S, S, S, 3)

    # 1. Mise à l'échelle des couleurs vers les indices de la LUT [0, size-1]
    coords = img_float * (size - 1)

    # 2. Calcul des indices des 8 coins du cube environnant
    c0 = np.floor(coords).astype(np.int32)
    c1 = np.ceil(coords).astype(np.int32)

    # Clamp pour éviter les index out of bounds (ex: valeur 1.0 -> index size)
    c0 = np.clip(c0, 0, size - 1)
    c1 = np.clip(c1, 0, size - 1)

    # 3. Calcul des poids d'interpolation (fraction partie décimale)
    # d = x - floor(x)
    d = coords - c0

    # On sépare les canaux pour la clarté du calcul
    # d_r, d_g, d_b shape: (H, W)
    d_r = d[..., 0:1]
    d_g = d[..., 1:2]
    d_b = d[..., 2:3]

    # Indices pour les 8 coins
    r0, g0, b0 = c0[..., 0], c0[..., 1], c0[..., 2]
    r1, g1, b1 = c1[..., 0], c1[..., 1], c1[..., 2]

    # 4. Échantillonnage des 8 coins
    # On utilise l'indexation avancée de NumPy
    # On récupère les 3 canaux de couleur pour chaque coin
    c000 = lut[r0, g0, b0]
    c100 = lut[r1, g0, b0]
    c010 = lut[r0, g1, b0]
    c110 = lut[r1, g1, b0]
    c001 = lut[r0, g0, b1]
    c101 = lut[r1, g0, b1]
    c011 = lut[r0, g1, b1]
    c111 = lut[r1, g1, b1]

    # 5. Interpolation trilinéaire
    # Axe R
    c00 = c000 * (1 - d_r) + c100 * d_r
    c01 = c001 * (1 - d_r) + c101 * d_r
    c10 = c010 * (1 - d_r) + c110 * d_r
    c11 = c011 * (1 - d_r) + c111 * d_r

    # Axe G
    c0 = c00 * (1 - d_g) + c10 * d_g
    c1 = c01 * (1 - d_g) + c11 * d_g

    # Axe B
    res = c0 * (1 - d_b) + c1 * d_b

    return np.clip(res, 0, 1)


def apply_vibrance(img_float: np.ndarray, amount: float = 0.15) -> np.ndarray:
    """
    Vibrance : boost la saturation des pixels peu saturés tout en préservant
    les pixels déjà très saturés et les tons chair.
    amount : [-1, 1]. Positive = boost, Négative = réduction.
    """
    if amount == 0:
        return img_float

    # Conversion float32 [0,1] -> uint8 [0,255] pour OpenCV
    img_uint8 = (img_float * 255).astype(np.uint8)
    hsv = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2HSV).astype(np.float32)

    # H: [0, 180], S: [0, 255], V: [0, 255]
    # Normalisons S vers [0, 1]
    s = hsv[..., 1] / 255.0
    v = hsv[..., 2] / 255.0

    # Formule de vibrance : on booste la saturation proportionnellement
    # à la faible saturation actuelle.
    # On utilise un facteur de pondération basé sur la saturation pour
    # éviter de saturer les couleurs déjà vives.
    # s_boost = amount * (1 - s)

    # Pour une vibrance naturelle, on peut aussi pondérer par la luminosité (v)
    # pour éviter de brûler les hautes lumières.
    s_boost = amount * (1.0 - s) * v

    # Application du boost
    s = np.clip(s + s_boost, 0, 1)

    # Retour vers uint8
    hsv[..., 1] = s * 255.0
    img_res_uint8 = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)

    return img_res_uint8.astype(np.float32) / 255.0


class LutEngine:
    """
    Moteur de gestion des LUTs. Gère le chargement, le cache et l'application.
    """
    def __init__(self, lut_dir: str):
        self.lut_dir = Path(lut_dir)
        self._cache = {}

    def list_luts(self) -> List[str]:
        """Liste les fichiers .cube disponibles dans le dossier."""
        if not self.lut_dir.exists():
            return []
        return [p.name for p in self.lut_dir.glob("*.cube")]

    def _get_lut_data(self, lut_name: str) -> Tuple[np.ndarray, int]:
        """Charge la LUT via le cache module-level (clé : dossier + nom).

        Le cache est partagé entre toutes les instances et persiste dans le
        process worker → le .cube n'est lu/parsé qu'UNE fois par lot.
        """
        return _load_lut_cached(str(self.lut_dir), lut_name)

    def apply(self, img_float: np.ndarray, lut_name: Optional[str], strength: float = 1.0) -> np.ndarray:
        """
        Applique une LUT spécifique avec une intensité donnée.
        strength = 0: original, 1: full LUT.
        """
        if lut_name is None or strength <= 0:
            return img_float

        try:
            lut, size = self._get_lut_data(lut_name)
            graded = apply_lut(img_float, lut, size)

            if strength < 1.0:
                # Mélange linéaire entre l'image originale et la version étalonnée
                return img_float * (1.0 - strength) + graded * strength

            return graded
        except Exception as e:
            # En cas d'erreur de lecture/application, on retourne l'original
            # On pourrait logger l'erreur ici
            return img_float
