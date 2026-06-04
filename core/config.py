"""
core/config.py — Persistance des réglages utilisateur
=====================================================
Stocke un JSON dans %APPDATA%/StudioPhoto/settings.json.
"""

import json
from pathlib import Path

_CONFIG_PATH = Path.home() / "AppData" / "Roaming" / "StudioPhoto" / "settings.json"

_DEFAULTS = {
    "grade_source":   "",
    "grade_output":   "",
    "grade_suffix":   "_graded",
    "grade_recursive": True,
    "grade_skip":      True,
    "grade_workers":   6,
    "grade_quality":   95,
    "rename_base":     "",
    "rename_include_root": False,
    "rename_dryrun":   True,
}


def load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
