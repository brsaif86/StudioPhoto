"""
core/renaming.py — Moteur de renommage séquentiel
==================================================
Fonctions pures, sans dépendance UI.
"""

import os
import re
import uuid
from pathlib import Path

RENAME_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".bmp", ".webp"}


def rename_folder(
    folder_path: str,
    folder_name: str,
    log,
    dry_run: bool = False,
) -> tuple:
    """Renomme les images d'un dossier en folder_name_001.ext (collision-safe).

    Retourne (nb_renommés, nb_déjà_ok).
    """
    all_files = sorted([
        f for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in RENAME_EXTS
    ])

    if not all_files:
        log(f"  {folder_name} : aucune image, ignoré.")
        return 0, 0

    pattern = re.compile(
        r"^" + re.escape(folder_name) + r"_(\d+)\.(jpg|jpeg|png|tif|tiff|gif|bmp|webp)$",
        re.IGNORECASE,
    )

    already_renamed: dict[int, str] = {}
    to_rename: list[str] = []
    for f in all_files:
        m = pattern.match(f)
        if m:
            already_renamed[int(m.group(1))] = f
        else:
            to_rename.append(f)

    existing_numbers = set(already_renamed.keys())
    next_num = max(existing_numbers) + 1 if existing_numbers else 1

    if not to_rename:
        log(f"  {folder_name} : tout est déjà renommé ({len(already_renamed)} fichiers).")
        _check_gaps(already_renamed, log)
        return 0, len(already_renamed)

    log(
        f"  {folder_name} : {len(already_renamed)} déjà OK, "
        f"{len(to_rename)} à renommer (reprise à _{next_num:03d})"
    )

    rename_plan: list[tuple[str, str]] = []
    for f in to_rename:
        while next_num in existing_numbers:
            next_num += 1
        ext = os.path.splitext(f)[1].lower()
        new_name = f"{folder_name}_{next_num:03d}{ext}"
        rename_plan.append((f, new_name))
        existing_numbers.add(next_num)
        next_num += 1

    if dry_run:
        for old_name, new_name in rename_plan:
            log(f"    [aperçu] {old_name} → {new_name}")
        return len(rename_plan), len(already_renamed)

    # Passe 1 : renommage vers noms temporaires
    temp_map: list[tuple[str, str]] = []
    for old_name, new_name in rename_plan:
        ext_tmp = os.path.splitext(old_name)[1].lower()
        temp_name = f"__tmp_{uuid.uuid4().hex}{ext_tmp}"
        os.rename(
            os.path.join(folder_path, old_name),
            os.path.join(folder_path, temp_name),
        )
        temp_map.append((temp_name, new_name))

    # Passe 2 : renommage vers noms définitifs
    renamed = 0
    for temp_name, new_name in temp_map:
        dest = os.path.join(folder_path, new_name)
        if os.path.exists(dest):
            log(f"    ⚠ Conflit : {new_name} existe déjà, temp conservé : {temp_name}")
        else:
            os.rename(os.path.join(folder_path, temp_name), dest)
            log(f"    → {new_name}")
            renamed += 1

    _check_gaps(already_renamed | {int(pattern.match(new_name).group(1)): new_name
                                    for _, new_name in rename_plan
                                    if pattern.match(new_name)}, log)
    return renamed, len(already_renamed)


def _check_gaps(already_renamed: dict, log) -> None:
    numbers = sorted(already_renamed.keys())
    if not numbers:
        return
    gaps = [numbers[i] for i in range(1, len(numbers)) if numbers[i] != numbers[i - 1] + 1]
    if gaps:
        log(f"  ⚠ Trous détectés après numéros : {gaps}")


def collect_rename_targets(base: Path, include_root: bool) -> list[tuple[str, str]]:
    """Retourne la liste (folder_path, folder_name) à traiter."""
    targets: list[tuple[str, str]] = []
    if include_root:
        targets.append((str(base), base.name))
    for name in sorted(os.listdir(base)):
        p = base / name
        if p.is_dir():
            targets.append((str(p), name))
    return targets
