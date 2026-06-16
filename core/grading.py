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


# ── Étalonnage couleur adaptatif (v3 original — rendu naturel préféré client) ──

def apply_color_grade(arr: np.ndarray, m: dict) -> Image.Image:
    """Étalonnage naturel & cinématographique ADAPTATIF (v3 original).

    Rendu doux/naturel : WB adaptative, shadow lift, S-curve douce (corps sans
    durcir), correction peau, légère désaturation, neutralisation des blancs.
    arr normalisé 0..1, modifié en place ; renvoie une image PIL.
    """
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
    if mean_lum > 0.60:
        lift = 0.008
    elif mean_lum > 0.50:
        lift = 0.012
    else:
        lift = 0.018
    arr *= (1 - lift)
    arr += lift

    # 3. S-curve adaptative (sin) — ajoute du corps sans durcir
    if std_lum > 0.20:
        curve_strength = 0.02
    elif std_lum > 0.15:
        curve_strength = 0.03
    else:
        curve_strength = 0.04
    arr += curve_strength * np.sin(np.pi * arr) * (1 - arr) * arr * 4

    # 4. Correction peau — neutralise les zones orange
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

    # 5. Désaturation légère (7 %)
    lum_map = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2])[:, :, np.newaxis]
    arr *= 0.93
    arr += lum_map * 0.07
    np.clip(arr, 0, 1, out=arr)

    # 6. Gamma lift adaptatif
    if mean_lum < 0.45:
        arr **= 0.97
    elif mean_lum < 0.55:
        arr **= 0.99

    # 7. Neutralisation des blancs adaptative (douce sur studio blanc)
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


def apply_color_grade_warm(arr: np.ndarray, m: dict) -> Image.Image:
    """« Naturel 2 » — couleurs naturelles fidèles + touche cinématique.

    v3 d'abord (base naturelle fidèle), puis une teinte d'ambiance très dosée :
    légère chaleur sur les midtones (blancs/noirs intacts), hautes lumières un
    soupçon chaudes, ombres un soupçon teal (teal & orange subtil), et une
    pointe de profondeur. Réf. d'ambiance : Dotan Maor / Esposa.
    """
    img = apply_color_grade(arr, m)                      # base v3 naturelle
    a = np.asarray(img, dtype=np.float32) / 255.0
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    skin = ((r > 0.45) & (g > 0.30) & (b < 0.60) & (r > g) & (g > b)).astype(np.float32)
    skin = np.asarray(
        Image.fromarray((skin * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(8)),
        dtype=np.float32,
    ) / 255.0

    # 1. Très légère chaleur sur les MIDTONES — fidèle aux couleurs naturelles,
    #    aucun voile : blancs (robe) et noirs intacts, peau tempérée.
    lum = (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2])
    mid = np.clip(1.0 - np.abs(lum - 0.48) / 0.40, 0.0, 1.0)      # cloche midtones
    w = 0.012 * mid * (1.0 - skin * 0.45)
    a[:, :, 0] *= 1.0 + w
    a[:, :, 2] *= 1.0 - w * 0.80
    np.clip(a, 0, 1, out=a)

    # 2. Touche CINÉMATIQUE subtile (teal & orange très dosé) : hautes lumières
    #    non blanches un soupçon chaudes, ombres un soupçon teal. Les couleurs
    #    restent fidèles — c'est une teinte d'ambiance, pas un filtre.
    lum = (0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2])
    not_white = np.clip((0.92 - lum) / 0.20, 0.0, 1.0)            # protège les blancs
    hi = ((lum ** 2) * not_white)[:, :, np.newaxis]
    sh = ((1.0 - lum) ** 2)[:, :, np.newaxis]
    a += hi * np.asarray([0.016, 0.007, -0.006], np.float32)      # HL légèrement chaudes
    a += sh * np.asarray([-0.006, 0.001, 0.008], np.float32)      # ombres légèrement teal
    np.clip(a, 0, 1, out=a)

    # 3. Légère profondeur (contraste doux côté ombres) — fonds romantiques.
    pivot = 0.45
    d = a - pivot
    a = pivot + d * np.where(d < 0.0, 1.12, 1.0)
    np.clip(a, 0, 1, out=a)
    return Image.fromarray((a * 255).astype(np.uint8))


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
