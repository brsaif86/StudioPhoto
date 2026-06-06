"""
build.py — Compile StudioPhoto en .exe autonome (robuste, multiplateforme)
==========================================================================
Remplace la logique fragile de build.bat (parsing cmd).
Usage : python build.py
Prérequis : pip install pyinstaller PySide6 Pillow numpy psutil
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)

SEP = ";" if os.name == "nt" else ":"   # séparateur --add-data


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def _on_rm_error(func, path, _exc):
    """Retire l'attribut lecture seule puis réessaie (fichiers Windows)."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _rmtree(path: Path) -> None:
    """shutil.rmtree compatible 3.11/3.12+ avec gestion lecture seule."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=lambda f, p, e: _on_rm_error(f, p, e))


def clean_previous(exe_name: str) -> bool:
    """Supprime build/ et dist/<exe> avant le build.

    Retourne False si un fichier reste verrouillé (app encore ouverte).
    """
    targets = [ROOT / "build", ROOT / "dist" / exe_name, ROOT / "dist" / f"{exe_name}.exe"]
    for t in targets:
        if not t.exists():
            continue
        try:
            _rmtree(t) if t.is_dir() else os.remove(t)
        except PermissionError:
            log("─" * 58)
            log("ERREUR : impossible de nettoyer dist/ — un fichier est VERROUILLÉ.")
            log("L'application StudioPhoto est probablement encore OUVERTE.")
            log("→ Ferme TOUTES les fenêtres de StudioPhoto puis relance le build.")
            log("  (Gestionnaire des tâches → terminer les StudioPhoto restants)")
            log("─" * 58)
            return False
        except Exception as exc:
            log(f"Nettoyage partiel ({t.name}) : {exc}")
    return True


def main() -> int:
    # 1. Version
    sys.path.insert(0, str(ROOT))
    try:
        from version import __version__
    except Exception as exc:
        log(f"Impossible de lire version.py : {exc}")
        return 1
    exe_name = f"StudioPhoto-{__version__}"
    log(f"Version : {__version__}  ->  {exe_name}")

    # 1b. Nettoyage des sorties précédentes (évite les verrous PyInstaller)
    if not clean_previous(exe_name):
        return 1

    # 2. Icône (régénère ICO + PNG carré si la source existe)
    if (ROOT / "app_icon.png").exists():
        log("Génération de l'icône carrée…")
        try:
            subprocess.run([sys.executable, "make_ico.py"], check=True)
        except subprocess.CalledProcessError as exc:
            log(f"make_ico.py a échoué ({exc}) — build sans icône personnalisée.")

    has_ico = (ROOT / "app_icon.ico").exists()
    has_sq  = (ROOT / "app_icon_square.png").exists()
    assets = ROOT / "assets"
    has_assets = assets.exists() and any(
        p.suffix in {".onnx", ".npy", ".json"} for p in assets.iterdir()
    )

    # Mode de packaging :
    #   --onefile : 1 exe (démarrage lent si gros modèle, ré-extraction temp)
    #   --onedir  : dossier exe + _internal (démarrage instantané) — défaut
    #               quand le modèle de classification est embarqué.
    # Forçable par variable d'env STUDIOPHOTO_ONEFILE=1.
    onefile = os.environ.get("STUDIOPHOTO_ONEFILE") == "1" or not has_assets
    mode_flag = "--onefile" if onefile else "--onedir"
    log(f"Mode packaging : {mode_flag}")

    # 3. Arguments PyInstaller
    # Dépendances DEV uniquement (export des assets) — jamais dans l'exe.
    DEV_ONLY = [
        "torch", "torchvision", "torchaudio", "open_clip", "open_clip_torch",
        "onnx", "onnxscript", "transformers", "sympy", "scipy",
    ]
    args = [
        sys.executable, "-m", "PyInstaller",
        mode_flag, "--windowed", "--noconfirm",
        "--name", exe_name,
        "--add-data", f"core{SEP}core",
        "--add-data", f"ui{SEP}ui",
        "--add-data", f"version.py{SEP}.",
    ]
    for mod in DEV_ONLY:
        args += ["--exclude-module", mod]
    if has_ico:
        args += ["--icon", "app_icon.ico", "--add-data", f"app_icon.ico{SEP}."]
    if has_sq:
        args += ["--add-data", f"app_icon_square.png{SEP}."]

    # Assets de classification (ONNX + embeddings) si présents
    if has_assets:
        log("Inclusion des assets de classification.")
        args += ["--add-data", f"assets{SEP}assets"]

    # Assets LUTs
    lut_assets = ROOT / "assets" / "luts"
    if lut_assets.exists() and any(lut_assets.iterdir()):
        log("Inclusion des LUTs.")
        args += ["--add-data", f"assets/luts{SEP}assets/luts"]
    else:
        log("Assets de classification absents — l'exe sera sans tri auto.")

    args.append("ui_entry.py")

    log("Lancement de PyInstaller…")
    log(" ".join(args))
    result = subprocess.run(args)
    if result.returncode != 0:
        log(f"ÉCHEC PyInstaller (code {result.returncode}).")
        return result.returncode

    ext = ".exe" if os.name == "nt" else ""
    if onefile:
        out = ROOT / "dist" / f"{exe_name}{ext}"
    else:
        out = ROOT / "dist" / exe_name / f"{exe_name}{ext}"
    log(f"OK — exécutable : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
