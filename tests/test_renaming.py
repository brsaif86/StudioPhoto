"""
tests/test_renaming.py — Tests du moteur de renommage
"""

import os
import tempfile
from pathlib import Path

import pytest

from core.renaming import rename_folder, collect_rename_targets


def make_images(folder: Path, names: list[str]) -> None:
    for n in names:
        (folder / n).write_bytes(b"\xff\xd8\xff\xe0")  # magic JPEG minimal


# ── Renommage de base ─────────────────────────────────────────────────────────

def test_rename_basic():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        make_images(folder, ["a.jpg", "b.jpg", "c.jpg"])

        log = []
        renamed, already_ok = rename_folder(str(folder), "mariage", log.__iadd__ or log.append, dry_run=False)

        assert renamed == 3
        assert already_ok == 0
        files = sorted(os.listdir(folder))
        assert "mariage_001.jpg" in files
        assert "mariage_002.jpg" in files
        assert "mariage_003.jpg" in files
        assert "a.jpg" not in files


def test_rename_dry_run_no_changes():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        make_images(folder, ["x.jpg", "y.jpg"])

        log_lines = []
        rename_folder(str(folder), "test", log_lines.append, dry_run=True)

        files = sorted(os.listdir(folder))
        assert "x.jpg" in files     # inchangé
        assert "y.jpg" in files
        assert any("[aperçu]" in l for l in log_lines)


def test_rename_resume_numbering():
    """Reprend la numérotation après les fichiers déjà nommés."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        make_images(folder, ["mariage_001.jpg", "mariage_002.jpg", "new.jpg"])

        log = []
        renamed, already_ok = rename_folder(str(folder), "mariage", log.append, dry_run=False)

        assert already_ok == 2
        assert renamed == 1
        assert (folder / "mariage_003.jpg").exists()


def test_rename_no_file_loss():
    """Deux passes garantissent qu'aucun fichier n'est écrasé ni perdu."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        names = [f"img{i:02d}.jpg" for i in range(1, 11)]
        make_images(folder, names)

        log = []
        rename_folder(str(folder), "shoot", log.append, dry_run=False)

        remaining = [f for f in os.listdir(folder) if f.endswith(".jpg")]
        assert len(remaining) == 10


def test_rename_empty_folder():
    with tempfile.TemporaryDirectory() as tmp:
        log = []
        renamed, ok = rename_folder(tmp, "empty", log.append, dry_run=False)
        assert renamed == 0
        assert ok == 0


def test_rename_skips_gap_reporting():
    """Des trous dans la séquence doivent être signalés."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        # Déjà renommés avec un trou : 1, 2, 4 (manque 3)
        make_images(folder, ["alpha_001.jpg", "alpha_002.jpg", "alpha_004.jpg"])

        log = []
        rename_folder(str(folder), "alpha", log.append, dry_run=False)

        # aucun nouveau fichier à renommer → la fonction doit détecter les trous
        assert any("Trous" in l or "trou" in l.lower() for l in log), \
            f"Trou non signalé. Log : {log}"


# ── collect_rename_targets ────────────────────────────────────────────────────

def test_collect_targets_subdirs_only():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "sub1").mkdir()
        (base / "sub2").mkdir()
        (base / "file.jpg").touch()

        targets = collect_rename_targets(base, include_root=False)
        paths = [t[0] for t in targets]
        assert str(base / "sub1") in paths
        assert str(base / "sub2") in paths
        assert str(base) not in paths


def test_collect_targets_include_root():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "sub").mkdir()

        targets = collect_rename_targets(base, include_root=True)
        paths = [t[0] for t in targets]
        assert str(base) in paths
