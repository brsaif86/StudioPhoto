"""
cli.py — Interface ligne de commande
=====================================
Réutilise le même core que l'UI. Aucune dépendance PySide6.

Usage :
    python cli.py grade /Photos/mariage --workers 6
    python cli.py grade /Photos --recursive --skip
    python cli.py rename /Photos --include-root
    python cli.py benchmark /Photos --workers 6 --workers 8 --sample 20
"""

import argparse
import multiprocessing as mp
import sys
import time
from pathlib import Path

from core.grading import DEFAULT_SUFFIX, DEFAULT_QUALITY, collect_grade_tasks, default_workers
from core.renaming import collect_rename_targets, rename_folder
from core.runner import run_grade_batch


# ── grade ──────────────────────────────────────────────────────────────────────

def cmd_grade(args) -> None:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"✗ Dossier introuvable : {folder}")

    output_dir = Path(args.output).resolve() if args.output else None

    print("=" * 60)
    print(f"  Source    : {folder}")
    print(f"  Sortie    : {output_dir or '_output (par dossier)'}")
    print(f"  Suffixe   : {args.suffix}")
    print(f"  Récursif  : {'oui' if args.recursive else 'non'}")
    print(f"  Skip      : {'oui' if args.skip else 'non'}")
    print(f"  Processus : {args.workers}")
    print("=" * 60)

    result = run_grade_batch(
        folder       = folder,
        suffix       = args.suffix,
        output_dir   = output_dir,
        recursive    = args.recursive,
        skip_existing= args.skip,
        workers      = args.workers,
        quality      = args.quality,
    )

    print("\n" + "=" * 60)
    print(f"  Terminé : {result['ok']} traitée(s), {result['skipped']} ignorée(s)"
          + (f", {result['errors']} erreur(s)" if result["errors"] else ""))
    print("=" * 60)


# ── rename ─────────────────────────────────────────────────────────────────────

def cmd_rename(args) -> None:
    base = Path(args.base).resolve()
    if not base.is_dir():
        sys.exit(f"✗ Dossier introuvable : {base}")

    dry_run = not args.real
    mode = "APERÇU" if dry_run else "RÉEL"
    print(f"  Mode : {mode}  |  Base : {base}\n")

    targets = collect_rename_targets(base, args.include_root)
    total_renamed = 0
    for path, name in targets:
        renamed, _ = rename_folder(path, name, print, dry_run)
        total_renamed += renamed

    verb = "à renommer (aperçu)" if dry_run else "renommée(s)"
    print(f"\n  Terminé : {total_renamed} image(s) {verb}.")


# ── benchmark ──────────────────────────────────────────────────────────────────

def cmd_benchmark(args) -> None:
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"✗ Dossier introuvable : {folder}")

    all_tasks = collect_grade_tasks(
        folder, args.suffix, None, args.recursive, skip_existing=False
    )
    if not all_tasks:
        sys.exit("Aucune image JPG trouvée.")

    sample = all_tasks[:args.sample] if args.sample else all_tasks
    print(f"\n  Benchmark — {len(sample)} image(s), dossier : {folder}")

    for w in args.workers:
        # Force skip=False pour mesurer le vrai traitement
        tasks_no_skip = [(inp, out, False, q) for inp, out, _, q in sample]

        import tempfile, os
        from core.grading import _grade_worker
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_tmp = [
                (inp, str(Path(tmpdir) / Path(inp).name), False, DEFAULT_QUALITY)
                for inp, _, _, _ in tasks_no_skip
            ]

            t0 = time.perf_counter()
            if w == 1:
                for t in tasks_tmp:
                    _grade_worker(t)
            else:
                pool = mp.Pool(processes=w)
                try:
                    list(pool.imap_unordered(_grade_worker, tasks_tmp))
                finally:
                    pool.close()
                    pool.join()
            elapsed = time.perf_counter() - t0

        throughput = len(sample) / elapsed
        print(f"    workers={w:2d}  →  {elapsed:.1f}s  ({throughput:.2f} img/s)")

    print()


# ── CLI entry ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Studio Photo — CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # grade
    g = sub.add_parser("grade", help="Étalonnage adaptatif v3")
    g.add_argument("folder")
    g.add_argument("--output", "-o", default=None)
    g.add_argument("--suffix", "-s", default=DEFAULT_SUFFIX)
    g.add_argument("--recursive", "-r", action="store_true", default=True)
    g.add_argument("--no-recursive", dest="recursive", action="store_false")
    g.add_argument("--skip", action="store_true", default=True)
    g.add_argument("--no-skip", dest="skip", action="store_false")
    g.add_argument("--workers", "-w", type=int, default=default_workers())
    g.add_argument("--quality", "-q", type=int, default=DEFAULT_QUALITY)

    # rename
    r = sub.add_parser("rename", help="Renommage séquentiel par dossier")
    r.add_argument("base")
    r.add_argument("--include-root", action="store_true", default=False)
    r.add_argument("--real", action="store_true", default=False,
                   help="Effectuer le renommage réel (défaut : aperçu)")

    # benchmark
    b = sub.add_parser("benchmark", help="Mesure le débit (images/s)")
    b.add_argument("folder")
    _dw = default_workers()
    b.add_argument("--workers", "-w", type=int, nargs="+", default=[_dw, min(_dw + 2, 16)])
    b.add_argument("--sample", "-n", type=int, default=20,
                   help="Nombre d'images à traiter (défaut : 20)")
    b.add_argument("--suffix", "-s", default=DEFAULT_SUFFIX)
    b.add_argument("--recursive", "-r", action="store_true", default=True)
    b.add_argument("--no-recursive", dest="recursive", action="store_false")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "grade":
        cmd_grade(args)
    elif args.cmd == "rename":
        cmd_rename(args)
    elif args.cmd == "benchmark":
        cmd_benchmark(args)


if __name__ == "__main__":
    mp.freeze_support()
    main()
