"""
ui/workers.py — QThread workers pour le traitement en arrière-plan
==================================================================
"""

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.grading import DEFAULT_SUFFIX, DEFAULT_QUALITY
from core.renaming import collect_rename_targets, rename_folder
from core.runner import run_grade_batch
from core.classification import run_classify_batch, DEFAULT_THRESHOLD


class GradeWorker(QThread):
    log_line    = Signal(str)
    progress    = Signal(int, int)          # (done, total)
    current     = Signal(str, str)          # (folder_name, file_name)
    speed       = Signal(float)             # images/sec
    eta         = Signal(int)               # seconds remaining
    finished    = Signal(dict)              # résumé final

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
            coherent_series = p.get("coherent", True),
            on_log       = self.log_line.emit,
            on_progress  = self.progress.emit,
            on_current   = self.current.emit,
            on_speed     = self.speed.emit,
            on_eta       = self.eta.emit,
            cancel_event = self._cancel,
        )
        result["cancelled"] = self._cancel.is_set()
        self.finished.emit(result)


class RenameWorker(QThread):
    log_line  = Signal(str)
    progress  = Signal(int, int)
    current   = Signal(str, str)          # (folder_name, "")
    finished  = Signal(int, bool)         # (total_renamed, dry_run)

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
            self.current.emit(name, "")
            renamed, _ = rename_folder(path, name, self.log_line.emit, dry_run)
            total_renamed += renamed
            self.progress.emit(i, len(targets))

        self.finished.emit(total_renamed, dry_run)


class ClassifyWorker(QThread):
    log_line  = Signal(str)
    progress  = Signal(int, int)          # (done, total)
    current   = Signal(str, str)          # (folder_name, file_name)
    speed     = Signal(float)             # images/sec
    eta       = Signal(int)               # seconds remaining
    finished  = Signal(dict)              # résumé final

    def __init__(self, params: dict, parent=None):
        super().__init__(parent)
        self._params = params
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        p = self._params
        result = run_classify_batch(
            folder       = p["folder"],
            output_dir   = p.get("output_dir"),
            mode         = p.get("mode", "manifest"),
            threshold    = p.get("threshold", DEFAULT_THRESHOLD),
            recursive    = p.get("recursive", True),
            batch_size   = p.get("batch_size", 16),
            on_log       = self.log_line.emit,
            on_progress  = self.progress.emit,
            on_current   = self.current.emit,
            on_speed     = self.speed.emit,
            on_eta       = self.eta.emit,
            cancel_event = self._cancel,
        )
        result["cancelled"] = self._cancel.is_set()
        self.finished.emit(result)
