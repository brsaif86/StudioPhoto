"""
core/config.py — Persistance des réglages utilisateur
=====================================================
Stocke un JSON dans %APPDATA%/StudioPhoto/settings.json.
"""

import json
from pathlib import Path

from core.grading import default_workers

_CONFIG_PATH = Path.home() / "AppData" / "Roaming" / "StudioPhoto" / "settings.json"


def _defaults() -> dict:
    return {
        "grade_source":        "",
        "grade_output":        "",
        "grade_suffix":        "_graded",
        "grade_recursive":     True,
        "grade_skip":          True,
        "grade_coherent":      True,    # série cohérente activée par défaut
        "grade_workers":       default_workers(),   # 60 % des coeurs physiques
        "grade_quality":       95,
        "rename_base":         "",
        "rename_include_root": False,
        "rename_dryrun":       True,
        "classify_source":     "",
        "classify_output":     "",
        "classify_mode":       "manifest",
        "classify_threshold":  0.45,
        "classify_batch":      16,
        "classify_recursive":  True,
    }


def load() -> dict:
    defaults = _defaults()
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return {**defaults, **data}
        except Exception:
            pass
    return defaults


def save(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
