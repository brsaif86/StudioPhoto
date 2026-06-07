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
            edit_global    = p.get("edit_global"),
            edits_by_path  = p.get("edits_by_path"),
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


class FewShotTrainWorker(QThread):
    """Entraîne (hors thread UI) la tête few-shot depuis des dossiers triés."""
    log_line = Signal(str)
    progress = Signal(int, int)            # (images encodées, total)
    finished = Signal(dict)                # {"ok", "labels", "n", "acc"} | {"ok":False,"error"}

    def __init__(self, train_dir, assets_dir=None, parent=None):
        super().__init__(parent)
        self._train_dir = train_dir
        self._assets_dir = assets_dir
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            from core.classification import Classifier
            from core.fewshot import train_from_folders, save_model, CancelledError
            self.log_line.emit("  Encodage CLIP des exemples…")
            embedder = Classifier(self._assets_dir)
            embedder.load()
            res = train_from_folders(
                self._train_dir, embedder,
                on_log=self.log_line.emit,
                on_progress=self.progress.emit,
                cancel_event=self._cancel,
            )
            path = save_model(res)
            self.log_line.emit(f"  → Modèle enregistré : {path}")
            self.finished.emit({"ok": True, "labels": res["labels"],
                                "n": res["n"], "acc": res["acc"]})
        except CancelledError:
            self.finished.emit({"ok": False, "error": "entraînement annulé"})
        except Exception as exc:
            self.finished.emit({"ok": False, "error": str(exc)})


class OllamaDetectWorker(QThread):
    """Détecte (hors thread UI) le serveur Ollama et ses modèles vision."""
    done = Signal(bool, list)        # (serveur_up, [noms_modèles_vision])

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from core.ollama_classify import server_up, list_vision_models
            if not server_up(self._url, timeout=4.0):
                self.done.emit(False, [])
                return
            self.done.emit(True, list_vision_models(self._url, timeout=8.0))
        except Exception:
            self.done.emit(False, [])


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
            engine       = p.get("engine", "hybrid"),
            ollama_model = p.get("ollama_model"),
            ollama_url   = p.get("ollama_url"),
            ollama_timeout = p.get("ollama_timeout", 300),
            hybrid_threshold = p.get("hybrid_threshold", 0.55),
            on_log       = self.log_line.emit,
            on_progress  = self.progress.emit,
            on_current   = self.current.emit,
            on_speed     = self.speed.emit,
            on_eta       = self.eta.emit,
            cancel_event = self._cancel,
        )
        result["cancelled"] = self._cancel.is_set()
        self.finished.emit(result)
