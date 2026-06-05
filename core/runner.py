"""
core/runner.py — Exécution parallèle du pipeline d'étalonnage
=============================================================
Séparé du moteur pour pouvoir être testé et utilisé en CLI sans importer l'UI.
"""

import multiprocessing as mp
import threading
import time
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
    coherent_series: bool = True,
    on_log: Callable[[str], None] = print,
    on_progress: Callable[[int, int], None] = None,
    on_current: Callable[[str, str], None] = None,  # (folder_name, file_name)
    on_speed: Callable[[float], None] = None,        # images/sec
    on_eta: Callable[[int], None] = None,            # seconds remaining
    cancel_event: threading.Event = None,
) -> dict:
    """Lance le traitement complet d'un dossier.

    Retourne {"ok": int, "skipped": int, "errors": int, "total": int}.
    """
    if coherent_series:
        on_log("  ⚙ Mode série cohérente : calcul du profil moyen par dossier…")
    tasks = collect_grade_tasks(
        folder, suffix, output_dir, recursive, skip_existing, quality, coherent_series
    )
    total = len(tasks)
    if total == 0:
        on_log("  Aucune image JPG trouvée.")
        return {"ok": 0, "skipped": 0, "errors": 0, "total": 0}

    if on_progress:
        on_progress(0, total)

    ok = err = skipped = 0
    t0 = time.perf_counter()
    # Moyenne glissante sur les 10 dernières images
    _times: list[float] = []

    def _handle(result: str, done: int, input_path: str) -> None:
        nonlocal ok, err, skipped
        on_log(result)
        ok      += "✓" in result
        skipped += "⏭" in result
        err     += "✗" in result

        elapsed = time.perf_counter() - t0
        _times.append(elapsed)
        if len(_times) > 10:
            _times.pop(0)

        # Vitesse sur fenêtre glissante
        if len(_times) >= 2:
            speed = (len(_times) - 1) / (_times[-1] - _times[0])
        else:
            speed = done / elapsed if elapsed > 0 else 0

        remaining = total - done
        eta = int(remaining / speed) if speed > 0 else 0

        p = Path(input_path)
        folder_name = p.parent.name
        file_name   = p.name

        if on_current:
            on_current(folder_name, file_name)
        if on_speed:
            on_speed(speed)
        if on_eta:
            on_eta(eta)
        if on_progress:
            on_progress(done, total)

    if workers > 1 and total > 1:
        pool = mp.Pool(processes=workers)
        try:
            done = 0
            for result, task in zip(
                pool.imap_unordered(_grade_worker, tasks), tasks
            ):
                if cancel_event and cancel_event.is_set():
                    pool.terminate()
                    break
                done += 1
                _handle(result, done, task[0])
        finally:
            pool.close()
            pool.join()
    else:
        for i, t in enumerate(tasks, 1):
            if cancel_event and cancel_event.is_set():
                break
            _handle(_grade_worker(t), i, t[0])

    return {"ok": ok, "skipped": skipped, "errors": err, "total": total}
