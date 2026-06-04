"""
ui/workers.py — QThread workers pour le traitement en arrière-plan
==================================================================
Séparation stricte : ces classes n'importent que le core, jamais de widgets.
"""

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core import config as cfg
from core.grading import DEFAULT_SUFFIX, DEFAULT_QUALITY
from core.renaming import collect_rename_targets, rename_folder
from core.runner import run_grade_batch


class GradeWorker(QThread):
    log_line   = Signal(str)
    progress   = Signal(int, int)   # (done, total)
    finished   = Signal(dict)       # résumé final

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self._params = params
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        p = self._params
        result = run_grade_batch(
            folder       = p["folder"],
            suffix       = p.get("suffix", DEFAULT_SUFFIX),
            output_dir   = p.get("output_dir"),
            recursive    = p.get("recursive", True),
            skip_existing= p.get("skip", True),
            workers      = p.get("workers", 6),
            quality      = p.get("quality", DEFAULT_QUALITY),
            on_log       = self.log_line.emit,
            on_progress  = self.progress.emit,
            cancel_event = self._cancel,
        )
        result["cancelled"] = self._cancel.is_set()
        self.finished.emit(result)


class RenameWorker(QThread):
    log_line  = Signal(str)
    progress  = Signal(int, int)
    finished  = Signal(int, bool)   # (total_renamed, dry_run)

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self._params = params
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        p = self._params
        base        = p["base"]
        include_root= p.get("include_root", False)
        dry_run     = p.get("dry_run", True)

        targets = collect_rename_targets(base, include_root)
        total_renamed = 0

        for i, (path, name) in enumerate(targets, 1):
            if self._cancel.is_set():
                break
            renamed, _ = rename_folder(path, name, self.log_line.emit, dry_run)
            total_renamed += renamed
            self.progress.emit(i, len(targets))

        self.finished.emit(total_renamed, dry_run)
