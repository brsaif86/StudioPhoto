"""
core/grading.py — Moteur d'étalonnage adaptatif v3
===================================================
Fonctions pures, sans dépendance UI.
Toutes les fonctions exécutées par les workers sont au niveau module (picklables).
"""

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG"}
DEFAULT_SUFFIX = "_graded"
DEFAULT_QUALITY = 95


def default_workers() -> int:
    """Retourne 60 % des cœurs physiques disponibles (min 1).

    Utilise psutil pour les cœurs physiques réels (sans hyperthreading).
    Repli sur os.cpu_count() // 2 si psutil absent.
    """
    try:
        import psutil
        physical = psutil.cpu_count(logical=False) or 1
    except ImportError:
        physical = max(1, (os.cpu_count() or 2) // 2)
    return max(1, math.ceil(physical * 0.6))


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


# ── Réglages du look « Naturel » (calés sur la réf. Esposa/Mimon) ─────────────
# Décale ici le rendu de BASE pour toutes les photos. Le dosage par photo/série
# se fait avec les curseurs de l'éditeur (Température, Contraste, Vignettage,
# Vibrance), qui s'empilent par-dessus.
NATUREL_WARMTH   = 0.012   # touche chaude golden (peau/midtones). 0 = neutre.
NATUREL_CONTRAST = 1.0     # multiplicateur de la courbe de contraste. 1 = défaut.
NATUREL_VIGNETTE = 0.12    # assombrissement des coins. 0 = aucun vignettage.


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

    # 1b. Récupération d'exposition — sur les images SUREXPOSÉES (visages/robe
    #     lavés), on redescend les TONS CLAIRS pour ramener le détail encore
    #     présent. Pondéré par la luminance → les ombres ne bougent pas. Le blanc
    #     PUR déjà clippé (sparklers, flash trop fort) reste irrécupérable.
    if highlight_ratio > 0.22 or mean_lum > 0.64:
        amt = float(np.clip((highlight_ratio - 0.18) * 0.7
                            + max(0.0, mean_lum - 0.60) * 0.6, 0.0, 0.20))
        if amt > 0:
            lum0 = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
            w = np.clip((lum0 - 0.45) / 0.55, 0.0, 1.0)[:, :, np.newaxis]
            arr *= (1.0 - amt * w)
            np.clip(arr, 0, 1, out=arr)

    # 2. Shadow lift adaptatif — bridé sur les images déjà claires (anti-surexpo)
    if mean_lum > 0.62 or highlight_ratio > 0.35:
        lift = 0.0                      # image lumineuse : ne pas ouvrir davantage
    elif mean_lum > 0.60:
        lift = 0.006
    elif mean_lum > 0.50:
        lift = 0.012
    else:
        lift = 0.018
    if lift:
        arr *= (1 - lift)
        arr += lift

    # 3. Contraste « riche » — S-curve autour d'un pivot bas : noirs plus
    #    profonds + hautes lumières dégagées (séparation tonale façon mariage pro,
    #    style Mimon/Esposa). Atténué sur les images sombres (anti-bouchage).
    pivot = 0.42
    contrast = (0.16 if std_lum > 0.20 else (0.22 if std_lum > 0.15 else 0.28)) * NATUREL_CONTRAST
    if mean_lum < 0.42:
        contrast *= 0.6
    elif mean_lum > 0.60 or highlight_ratio > 0.25:
        contrast *= 0.5      # image déjà chargée en hautes lumières → ne pas les pousser
    arr -= pivot
    arr *= (1.0 + contrast)
    arr += pivot
    np.clip(arr, 0, 1, out=arr)

    # 4. Correction peau adaptative
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    orange_mask = (
        (r > 0.45) & (g > 0.30) & (b < 0.60) & (r > g) & (g > b)
    ).astype(np.float32)

    mask_img = Image.fromarray((orange_mask * 255).astype(np.uint8))
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=8))
    orange_mask = np.asarray(mask_img, dtype=np.float32) / 255.0

    # Correction peau ADOUCIE : on retire moins de rouge et on ajoute très peu
    # de bleu → la peau garde sa chaleur naturelle (évite le teint terne/gris).
    skin_strength = 0.5 if warm_cast > 0.08 else 1.0
    arr[:, :, 0] -= orange_mask * arr[:, :, 0] * 0.015 * skin_strength
    arr[:, :, 2] += orange_mask * (1 - arr[:, :, 2]) * 0.005 * skin_strength

    # 5. Vibrance — booste la saturation des zones PEU saturées (verts, bleus,
    #    décor) en PROTÉGEANT la peau (masque peau + zones déjà saturées). Donne
    #    des couleurs riches et vivantes sans virer le teint (look Mimon/Esposa).
    lum_map = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])[:, :, np.newaxis]
    mx = arr.max(axis=2, keepdims=True)
    mn = arr.min(axis=2, keepdims=True)
    sat = (mx - mn) / (mx + 1e-6)
    vib = 0.22 * (1.0 - sat)                                   # + de boost si peu saturé
    vib *= (1.0 - orange_mask[:, :, np.newaxis] * 0.7)        # protège la peau
    arr[:] = lum_map + (arr - lum_map) * (1.0 + vib)
    np.clip(arr, 0, 1, out=arr)

    # 5b. Touche chaude « golden » très légère (peau/midtones). Les blancs sont
    #     re-neutralisés à l'étape 7 → chaleur sans jaunir la robe.
    arr[:, :, 0] *= 1.0 + NATUREL_WARMTH
    arr[:, :, 2] *= 1.0 - NATUREL_WARMTH * 0.83
    np.clip(arr, 0, 1, out=arr)

    # 6. Gamma lift adaptatif
    if mean_lum < 0.45:
        arr **= 0.97
    elif mean_lum < 0.55:
        arr **= 0.99

    # 6b. Anti-surexposition — rolloff doux des très hautes lumières
    #     Récupère du détail dans les blancs « cramés » sans grisailler la robe :
    #     seuls les pixels au-dessus de l'épaule (0.86) sont compressés, et
    #     d'autant plus que l'image est globalement claire.
    roll = 0.50 if (mean_lum > 0.62 or highlight_ratio > 0.30) else 0.22
    shoulder = 0.86
    over = np.clip((arr - shoulder) / (1.0 - shoulder), 0.0, 1.0)
    arr -= over * (arr - shoulder) * roll

    # 7. Neutralisation des blancs — protection anti-dominante (bleu/couleur)
    #    Les pixels très clairs (robe blanche, ciel) sont ramenés fortement vers
    #    le gris neutre afin qu'ils ne prennent AUCUNE teinte. Le poids monte
    #    progressivement avec la luminance (rampe 0.72 → 0.92) puis est lissé
    #    pour éviter tout liseré sur les bords.
    lum_w = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    whiteness = np.clip((lum_w - 0.72) / 0.20, 0.0, 1.0)

    whiteness = np.asarray(
        Image.fromarray((whiteness * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)),
        dtype=np.float32,
    ) / 255.0

    # Neutralisation forte sur les blancs (jusqu'à 0.92 → quasi R=G=B),
    # adoucie si l'image comporte déjà beaucoup de hautes lumières.
    max_neutral = 0.85 if highlight_ratio > 0.25 else 0.92
    avg = (arr[:, :, 0] + arr[:, :, 1] + arr[:, :, 2]) / 3.0
    factor = whiteness * max_neutral
    for c in range(3):
        arr[:, :, c] = arr[:, :, c] * (1 - factor) + avg * factor

    # 8. Vignettage léger — profondeur / dimension (subtil, façon portrait pro).
    h, w = arr.shape[:2]
    yy, xx = np.ogrid[:h, :w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    d = np.sqrt(((xx - cx) / (cx + 1e-6)) ** 2 + ((yy - cy) / (cy + 1e-6)) ** 2)
    vmask = (np.clip(d / 1.41, 0.0, 1.0) ** 2)[:, :, np.newaxis].astype(np.float32)
    arr *= (1.0 - NATUREL_VIGNETTE * vmask)

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
    profile: dict = None,
    edit=None,
) -> str:
    """Traite une image et retourne un message de statut.

    - Conversion numpy unique
    - Skip si la sortie existe déjà
    - Libération mémoire explicite
    - profile : si fourni (mode « série cohérente »), pilote les décisions
      adaptatives à partir des métriques MOYENNES du dossier.
    - edit : EditParams (preset + corrections). None/neutre = étalonnage v3.
    """
    try:
        if skip_existing and output_path.exists():
            return f"  ⏭ [Skip] {input_path.name} (déjà traité)"

        img = Image.open(input_path).convert("RGB")
        arr255 = np.asarray(img, dtype=np.float32)

        neutral = edit is None or getattr(edit, "is_neutral", lambda: True)()
        if neutral:
            # ── Chemin v3 strict (lot par défaut) — inchangé ──
            if is_grayscale(arr255):
                arr01  = arr255 / 255.0
                graded = apply_bw_grade(arr01)
                mode   = "N&B"
                info   = ""
            else:
                arr01  = arr255 / 255.0
                m      = profile if profile else analyze_image(arr01)
                graded = apply_color_grade(arr01, m)
                mode   = "Couleur" + ("·série" if profile else "")
                lum_label = (
                    "sombre"    if m["mean_lum"] < 0.45 else
                    "moyenne"   if m["mean_lum"] < 0.60 else
                    "lumineuse"
                )
                info = f"  | lum:{lum_label} cast:{m['warm_cast']:+.2f} hl:{m['highlight_ratio']:.0%}"
        else:
            # ── Éditeur : preset + corrections manuelles ──
            from core.adjustments import render_with_profile
            arr01 = arr255 / 255.0
            out01 = render_with_profile(arr01, edit, profile)
            graded = Image.fromarray((np.clip(out01, 0, 1) * 255).astype(np.uint8))
            mode = edit.label()
            info = "  | édité"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        graded.save(str(output_path), quality=quality, subsampling=0)

        del img, arr255, arr01, graded
        return f"  ✓ [{mode}] {input_path.name} → {output_path.name}{info}"

    except Exception as exc:
        return f"  ✗ ERREUR {input_path.name}: {exc}"


# ── Aperçu en mémoire (avant / après) ─────────────────────────────────────────

def grade_preview(input_path: Path, max_dim: int = 1600, profile: dict = None,
                  edit=None):
    """Étalonne une image EN MÉMOIRE et retourne (original, graded, mode, metrics).

    - Ne sauvegarde rien sur disque (usage : prévisualisation UI).
    - Réduit l'image si elle dépasse max_dim (aperçu rapide).
    - profile : mode « série cohérente » (preset Naturel).
    - edit : EditParams (preset + corrections). None/neutre = v3.
    Retourne (PIL.Image original, PIL.Image graded, str mode, dict metrics).
    """
    img = Image.open(input_path).convert("RGB")

    # Downscale pour l'aperçu (préserve le ratio)
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    original = img.copy()
    arr255 = np.asarray(img, dtype=np.float32)
    arr01  = arr255 / 255.0

    neutral = edit is None or getattr(edit, "is_neutral", lambda: True)()
    if neutral:
        if is_grayscale(arr255):
            graded = apply_bw_grade(arr01)
            mode, metrics = "N&B", {}
        else:
            metrics = profile if profile else analyze_image(arr01)
            graded  = apply_color_grade(arr01, metrics)
            mode    = "Couleur" + ("·série" if profile else "")
    else:
        from core.adjustments import render_with_profile
        out01  = render_with_profile(arr01, edit, profile)
        graded = Image.fromarray((np.clip(out01, 0, 1) * 255).astype(np.uint8))
        mode   = edit.label()
        metrics = profile if profile else analyze_image(arr01)

    return original, graded, mode, metrics


# ── Worker picklable (multiprocessing sous Windows) ───────────────────────────

def _ensure_std_streams() -> None:
    """Garantit sys.stdout/sys.stderr non-None dans les process enfants.

    Sous PyInstaller --windowed, les enfants du Pool héritent de flux None ;
    toute écriture (multiprocessing, warnings) plante alors sur None.write.
    """
    import sys

    class _Null:
        def write(self, *_a, **_k):
            return 0
        def flush(self):
            pass
        def isatty(self):
            return False

    if sys.stdout is None:
        sys.stdout = _Null()
    if sys.stderr is None:
        sys.stderr = _Null()


def _grade_worker(args: tuple) -> str:
    """Wrapper picklable pour mp.Pool."""
    _ensure_std_streams()
    input_path, output_path, skip_existing, quality, profile, edit = args
    return process_image(
        Path(input_path), Path(output_path), skip_existing, quality, profile, edit,
    )


# ── Collecte des tâches ───────────────────────────────────────────────────────

def collect_grade_tasks(
    folder: Path,
    suffix: str,
    output_dir,          # Path | None
    recursive: bool,
    skip_existing: bool,
    quality: int = DEFAULT_QUALITY,
    coherent_series: bool = False,
    on_log=None,
    edit_global=None,
    edits_by_path: dict = None,
) -> list:
    """Retourne la liste des tuples (input, output, skip, quality, profile, edit).

    - coherent_series=True : profil moyen calculé PAR DOSSIER (rendu uniforme).
    - edit_global : EditParams appliqué à toutes les images sans surcharge.
    - edits_by_path : {str(chemin): EditParams} surcharges par image.
    """
    edits_by_path = edits_by_path or {}
    candidates = folder.rglob("*") if recursive else folder.iterdir()

    files = sorted([
        p for p in candidates
        if p.suffix in SUPPORTED_EXTENSIONS
        and suffix not in p.stem
        and not p.name.startswith("._")
        and "_output" not in p.parts
    ])

    # Profils par dossier (calculés une seule fois, avec feedback)
    profiles: dict = {}
    if coherent_series:
        by_dir: dict = {}
        for p in files:
            by_dir.setdefault(p.parent, []).append(p)
        ndirs = len(by_dir)
        for i, (parent, group) in enumerate(by_dir.items(), 1):
            if on_log and (ndirs <= 30 or i % 5 == 0 or i == ndirs):
                on_log(f"  ⚙ Profil de série {i}/{ndirs} — {parent.name}")
            profiles[parent] = compute_folder_profile(group)

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
        profile = profiles.get(input_path.parent) if coherent_series else None
        edit = edits_by_path.get(str(input_path), edit_global)
        tasks.append(
            (str(input_path), str(out_path), skip_existing, quality, profile, edit)
        )
    return tasks


def list_source_images(folder: Path, suffix: str, recursive: bool) -> list:
    """Liste les images source d'un dossier (mêmes exclusions que la collecte).

    Sert à la prévisualisation : on ne veut pas inclure les fichiers déjà
    étalonnés (suffixe), les parasites macOS ni le dossier _output.
    """
    candidates = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        p for p in candidates
        if p.suffix in SUPPORTED_EXTENSIONS
        and suffix not in p.stem
        and not p.name.startswith("._")
        and "_output" not in p.parts
    )


def compute_folder_profile(files: list, sample_max: int = 20, max_dim: int = 384):
    """Calcule les métriques MOYENNES d'un ensemble d'images couleur.

    Échantillonne au plus `sample_max` images (réduites à `max_dim` px) pour
    rester rapide, ignore les N&B, et renvoie un dict de métriques moyen
    (mean_lum, std_lum, warm_cast, highlight_ratio) ou None si rien d'exploitable.
    """
    if not files:
        return None
    files = sorted(files)
    step = max(1, len(files) // sample_max)
    sample = files[::step][:sample_max]

    keys = ("mean_lum", "std_lum", "warm_cast", "highlight_ratio")
    accum = {k: 0.0 for k in keys}
    n = 0
    for p in sample:
        try:
            img = Image.open(p).convert("RGB")
            w, h = img.size
            if max(w, h) > max_dim:
                s = max_dim / max(w, h)
                img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
            arr255 = np.asarray(img, dtype=np.float32)
            if is_grayscale(arr255):
                continue
            m = analyze_image(arr255 / 255.0)
            for k in keys:
                accum[k] += m[k]
            n += 1
        except Exception:
            continue
    if n == 0:
        return None
    return {k: accum[k] / n for k in keys}
