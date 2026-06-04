"""
core/runner.py — Exécution parallèle du pipeline d'étalonnage
=============================================================
Séparé du moteur pour pouvoir être testé et utilisé en CLI sans importer l'UI.
"""

import multiprocessing as mp
import threading
from pathlib import Path
from typing import Callable

from core.grading import _grade_worker, collect_grade_tasks, DEFAULT_SUFFIX, DEFAULT_QUALITY


def run_grade_batch(
    folder: Path,
    suffix: str = DEFAULT_SUFFIX,
    output_dir=None,
    recursive: bool = True,
    skip_existing: bool = True,
    workers: int = 6,
    quality: int = DEFAULT_QUALITY,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = None,
    cancel_event: threading.Event = None,
) -> dict:
    """Lance le traitement complet d'un dossier.

    Retourne {"ok": int, "skipped": int, "errors": int, "total": int}.
    """
    tasks = collect_grade_tasks(folder, suffix, output_dir, recursive, skip_existing, quality)
    total = len(tasks)
    if total == 0:
        on_log("  Aucune image JPG trouvée.")
        return {"ok": 0, "skipped": 0, "errors": 0, "total": 0}

    if on_progress:
        on_progress(0, total)

    ok = err = skipped = 0

    def _handle(result: str, done: int) -> None:
        nonlocal ok, err, skipped
        on_log(result)
        ok      += "✓" in result
        skipped += "⏭" in result
        err     += "✗" in result
        if on_progress:
            on_progress(done, total)

    if workers > 1 and total > 1:
        pool = mp.Pool(processes=workers)
        try:
            done = 0
            for result in pool.imap_unordered(_grade_worker, tasks):
                if cancel_event and cancel_event.is_set():
                    pool.terminate()
                    break
                done += 1
                _handle(result, done)
        finally:
            pool.close()
            pool.join()
    else:
        for i, t in enumerate(tasks, 1):
            if cancel_event and cancel_event.is_set():
                break
            _handle(_grade_worker(t), i)

    return {"ok": ok, "skipped": skipped, "errors": err, "total": total}
