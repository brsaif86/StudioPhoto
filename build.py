"""
build.py — Compile StudioPhoto en .exe autonome (robuste, multiplateforme)
==========================================================================
Remplace la logique fragile de build.bat (parsing cmd).
Usage : python build.py
Prérequis : pip install pyinstaller PySide6 Pillow numpy psutil
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)

SEP = ";" if os.name == "nt" else ":"   # séparateur --add-data


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


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
