"""
core/grading.py — Moteur d'étalonnage adaptatif v3
===================================================
Fonctions pures, sans dépendance UI.
Toutes les fonctions exécutées par les workers sont au niveau module (picklables).
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG"}
DEFAULT_SUFFIX = "_graded"
DEFAULT_QUALITY = 95


# ── Détection N&B ─────────────────────────────────────────────────────────────

def is_grayscale(arr255: np.ndarray, threshold: float = 3.0) -> bool:
    diff_rg = np.mean(np.abs(arr255[:, :, 0] - arr255[:, :, 1]))
    diff_rb = np.mean(np.abs(arr255[:, :, 0] - arr255[:, :, 2]))
    return diff_rg < threshold and diff_rb < threshold


# ── Analyse ───────────────────────────────────────────────────────────────────

def analyze_image(arr: np.ndarray) -> dict:
    """Analyse luminosité, contraste et dominante couleur (arr en 0..1)."""
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    return {
        "mean_lum":        float(np.mean(lum)),
        "std_lum":         float(np.std(lum)),
        "warm_cast":       float(np.mean(arr[:, :, 0])) - float(np.mean(arr[:, :, 2])),
        "highlight_ratio": float(np.mean(lum > 0.80)),
    }


# ── Étalonnage couleur adaptatif v3 ───────────────────────────────────────────

def apply_color_grade(arr: np.ndarray, m: dict) -> Image.Image:
    """Étalonnage couleur ADAPTATIF (v3). arr normalisé 0..1, modifié en place."""
    mean_lum        = m["mean_lum"]
    std_lum         = m["std_lum"]
    warm_cast       = m["warm_cast"]
    highlight_ratio = m["highlight_ratio"]

    # 1. Balance des blancs adaptative
    wb_strength = 1.0
    if mean_lum > 0.60:
        wb_strength = 0.4
    elif mean_lum > 0.50:
        wb_strength = 0.7
    if warm_cast < 0.03:
        wb_strength *= 0.5

    arr[:, :, 0] *= 1.0 - 0.03 * wb_strength
    arr[:, :, 1] *= 1.0 - 0.02 * wb_strength
    arr[:, :, 2] *= 1.0 + 0.01 * wb_strength

    # 2. Shadow lift adaptatif
    lift = 0.008 if mean_lum > 0.60 else (0.012 if mean_lum > 0.50 else 0.018)
    arr *= (1 - lift)
    arr += lift

    # 3. S-curve adaptative
    curve_strength = 0.02 if std_lum > 0.20 else (0.03 if std_lum > 0.15 else 0.04)
    arr += curve_strength * np.sin(np.pi * arr) * (1 - arr) * arr * 4

    # 4. Correction peau adaptative
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    orange_mask = (
        (r > 0.45) & (g > 0.30) & (b < 0.60) & (r > g) & (g > b)
    ).astype(np.float32)

    mask_img = Image.fromarray((orange_mask * 255).astype(np.uint8))
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=8))
    orange_mask = np.asarray(mask_img, dtype=np.float32) / 255.0

    skin_strength = 0.5 if warm_cast > 0.08 else 1.0
    arr[:, :, 0] -= orange_mask * arr[:, :, 0] * 0.03 * skin_strength
    arr[:, :, 2] += orange_mask * (1 - arr[:, :, 2]) * 0.015 * skin_strength

    # 5. Désaturation légère
    lum_map = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])[:, :, np.newaxis]
    arr *= 0.93
    arr += lum_map * 0.07
    np.clip(arr, 0, 1, out=arr)

    # 6. Gamma lift adaptatif
    if mean_lum < 0.45:
        arr **= 0.97
    elif mean_lum < 0.55:
        arr **= 0.99

    # 7. Neutralisation des blancs adaptative
    nw_strength = 0.15 if highlight_ratio > 0.25 else 0.30
    near_white = (
        (arr[:, :, 0] > 0.75) & (arr[:, :, 1] > 0.75) & (arr[:, :, 2] > 0.70)
    ).astype(np.float32)

    nw_smooth = np.asarray(
        Image.fromarray((near_white * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)),
        dtype=np.float32,
    ) / 255.0

    avg = (arr[:, :, 0] + arr[:, :, 1] + arr[:, :, 2]) / 3.0
    factor = nw_smooth * nw_strength
    for c in range(3):
        arr[:, :, c] = arr[:, :, c] * (1 - factor) + avg * factor

    np.clip(arr, 0, 1, out=arr)
    return Image.fromarray((arr * 255).astype(np.uint8))


# ── Étalonnage N&B ────────────────────────────────────────────────────────────

def apply_bw_grade(arr: np.ndarray) -> Image.Image:
    """Étalonnage N&B (arr normalisé 0..1, modifié en place)."""
    lift = 0.015
    arr *= (1 - lift)
    arr += lift
    arr += 0.03 * np.sin(np.pi * arr) * (1 - arr) * arr * 4
    np.clip(arr, 0, 1, out=arr)
    return Image.fromarray((arr * 255).astype(np.uint8))


# ── Traitement d'une image ────────────────────────────────────────────────────

def process_image(
    input_path: Path,
    output_path: Path,
    skip_existing: bool = True,
    quality: int = DEFAULT_QUALITY,
) -> str:
    """Traite une image et retourne un message de statut.

    - Conversion numpy unique
    - Skip si la sortie existe déjà
    - Libération mémoire explicite
    """
    try:
        if skip_existing and output_path.exists():
            return f"  ⏭ [Skip] {input_path.name} (déjà traité)"

        img = Image.open(input_path).convert("RGB")
        arr255 = np.asarray(img, dtype=np.float32)

        if is_grayscale(arr255):
            arr01  = arr255 / 255.0
            graded = apply_bw_grade(arr01)
            mode   = "N&B"
            info   = ""
        else:
            arr01  = arr255 / 255.0
            m      = analyze_image(arr01)
            graded = apply_color_grade(arr01, m)
            mode   = "Couleur"
            lum_label = (
                "sombre"    if m["mean_lum"] < 0.45 else
                "moyenne"   if m["mean_lum"] < 0.60 else
                "lumineuse"
            )
            info = f"  | lum:{lum_label} cast:{m['warm_cast']:+.2f} hl:{m['highlight_ratio']:.0%}"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        graded.save(str(output_path), quality=quality, subsampling=0)

        del img, arr255, arr01, graded
        return f"  ✓ [{mode}] {input_path.name} → {output_path.name}{info}"

    except Exception as exc:
        return f"  ✗ ERREUR {input_path.name}: {exc}"


# ── Worker picklable (multiprocessing sous Windows) ───────────────────────────

def _grade_worker(args: tuple) -> str:
    """Wrapper picklable pour mp.Pool."""
    input_path, output_path, skip_existing, quality = args
    return process_image(Path(input_path), Path(output_path), skip_existing, quality)


# ── Collecte des tâches ───────────────────────────────────────────────────────

def collect_grade_tasks(
    folder: Path,
    suffix: str,
    output_dir,          # Path | None
    recursive: bool,
    skip_existing: bool,
    quality: int = DEFAULT_QUALITY,
) -> list:
    """Retourne la liste des tuples (input, output, skip, quality) à traiter."""
    candidates = folder.rglob("*") if recursive else folder.iterdir()

    files = sorted([
        p for p in candidates
        if p.suffix in SUPPORTED_EXTENSIONS
        and suffix not in p.stem
        and not p.name.startswith("._")
        and "_output" not in p.parts
    ])

    tasks = []
    for input_path in files:
        if output_dir:
            try:
                relative = input_path.relative_to(folder)
            except ValueError:
                relative = Path(input_path.name)
            out_name = relative.with_name(relative.stem + suffix + relative.suffix)
            out_path = output_dir / out_name
        else:
            out_path = input_path.parent / "_output" / (
                input_path.stem + suffix + input_path.suffix
            )
        tasks.append((str(input_path), str(out_path), skip_existing, quality))
    return tasks
