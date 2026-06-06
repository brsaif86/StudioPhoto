# StudioPhoto

Application photo autonome (Windows / macOS) regroupant **4 outils** :

1. **Étalonnage adaptatif v3** — couleur + N&B, multiprocessing, anti-surexposition,
   mode série cohérente, blancs neutres. Reprise de lot.
2. **Aperçu** — comparateur avant/après à curseur (rendu identique au lot).
3. **Classification / Tri auto** — zero-shot CLIP (OpenCV + onnxruntime, sans torch
   au runtime) en 6 catégories de mariage + « À revoir ».
4. **Renommage séquentiel** — par dossier, two-pass, dry-run, reprise.

Version courante : voir `version.py` (`__version__`). Le titre de la fenêtre, le nom
de l'exe et les artefacts CI en découlent.

---

## Prérequis développeur

- Python 3.11+
- `pip install -r requirements.txt`

```
Pillow  numpy  PySide6  psutil  opencv-python-headless  onnxruntime  pyinstaller  pytest
```

> `requirements-dev.txt` ajoute torch / open_clip / onnx — **uniquement** pour
> générer le modèle de classification hors-ligne (jamais embarqué dans l'exe).

---

## Lancer l'application

```bat
python ui_entry.py
```

Sidebar : **Étalonnage · Aperçu · Classification · Renommage**.

---

## Utilisation CLI

```bat
# ── Étalonnage (récursif, ~60% des cœurs physiques, série cohérente ON) ──
python cli.py grade C:\Photos\Mariage
python cli.py grade C:\Photos --workers 8 --output C:\Out --suffix _edit
python cli.py grade C:\Photos --no-coherent          # étalonnage par image

# ── Renommage ──
python cli.py rename C:\Photos                        # aperçu (dry-run)
python cli.py rename C:\Photos --real                 # renommage réel

# ── Classification (tri auto) ──
python cli.py classify C:\Photos                      # manifest results.json (non destructif)
python cli.py classify C:\Photos --mode copy          # copie dans sous-dossiers
python cli.py classify C:\Photos --mode move --yes    # déplacement (confirmation requise)
python cli.py classify C:\Photos --threshold 0.5      # seuil « À revoir »

# ── Benchmark étalonnage ──
python cli.py benchmark C:\Photos --workers 6 8 --sample 20
```

---

## Classification — catégories & modèle

6 classes (l'ordre **est** le mapping) + « À revoir » sous le seuil :

`Preparations · Love Story · Atmosphere · Family · Ktuba and Huppa · Dance`

Pipeline : `cv2` (décodage/prétraitement) → encodeur image CLIP **ONNX** exécuté
par **onnxruntime** → similarité avec des **embeddings texte précalculés** →
softmax × `logit_scale`. Aucun torch au runtime.

### Générer le modèle (une fois, sur machine dev)

```bat
pip install -r requirements-dev.txt
python tools\export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k
```

Produit dans `assets/` (exclus du dépôt car volumineux) :
`mobileclip_image.onnx` · `text_embeddings.npy` · `clip_meta.json`.

Sans ces fichiers, l'onglet Classification affiche un avertissement ; le reste de
l'app fonctionne normalement.

### Précision mesurée (jeu client étiqueté, ViT-B-32)

| Catégorie | Précision |
|-----------|-----------|
| Ktuba and Huppa | ~95 % |
| Dance | ~92 % |
| Love Story | ~88 % |
| Atmosphere / Family | plus faibles (taxonomie client subjective) |

> Les classes visuellement nettes sont fiables ; « Atmosphere » mélange lieux vides
> et invités candides, intrinsèquement ambigu. Utiliser le mode `manifest`
> (non destructif) pour réviser avant tout tri physique.

---

## Tests

```bat
pytest tests/ -v
```

- `test_grading.py` — étalonnage v3 (dont régression pixel `RMSE < 2/255`,
  blancs neutres, anti-surexposition, profil série).
- `test_renaming.py` — renommage (2 passes, dry-run, reprise, trous).
- `test_classification.py` — preprocess, softmax/seuil, mapping, manifest,
  isolation des images corrompues.

---

## Build exe

```bat
build.bat            REM appelle python build.py
```

ou directement `python build.py`.

- Lit la version depuis `version.py` → `dist\StudioPhoto-<version>(.exe)`.
- Génère l'icône carrée, exclut torch et les dépendances dev.
- **`--onedir` par défaut si le modèle est dans `assets/`** (démarrage instantané,
  lanceur léger) ; sinon **`--onefile`**.
- Forcer le fichier unique : `set STUDIOPHOTO_ONEFILE=1 && python build.py`.

Distribution : zipper le dossier `dist\StudioPhoto-<version>\` (modèle inclus) ;
l'utilisateur dézippe et double-clique — aucune installation, aucun Python requis.

---

## Build macOS (Intel & Apple Silicon)

PyInstaller **ne fait pas de cross-compilation** : il faut builder **sur** un Mac,
et le binaire produit correspond à l'architecture de cette machine
(`arm64` sur Apple Silicon, `x86_64` sur Intel).

### Méthode rapide (script fourni)

```bash
chmod +x build_mac.sh
./build_mac.sh
```

Le script crée le venv, installe les dépendances, lance les tests et build.

### Méthode manuelle (pas à pas)

```bash
# 1. Python 3.11 (si besoin)
brew install python@3.11

# 2. Récupérer le projet
git clone https://github.com/brsaif86/StudioPhoto.git
cd StudioPhoto

# 3. Environnement + dépendances (sans torch)
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. (Optionnel) Modèle de classification dans assets/
#    - soit copier le dossier assets/ depuis une autre machine,
#    - soit le régénérer :
#        pip install -r requirements-dev.txt
#        python tools/export_clip_assets.py --model ViT-B-32 --pretrained laion2b_s34b_b79k

# 5. Tester puis builder
python -m pytest tests/ -q
python build.py            # --onedir si assets/ présents, sinon --onefile
```

### Lancer / distribuer sur Mac

```bash
# Lancement
open dist/StudioPhoto-<version>/StudioPhoto-<version>      # onedir
# ou ./dist/StudioPhoto-<version>                          # onefile

# 1er lancement bloqué par Gatekeeper (app non signée) :
xattr -dr com.apple.quarantine dist/StudioPhoto-*
# ou : clic droit sur l'app → Ouvrir → Ouvrir
```

> **Architecture** : sur un iMac Intel, le binaire produit est `x86_64` —
> c'est le build Intel que la CI GitHub ne fournit pas (voir ci-dessous).
> `build.py` gère seul le séparateur `:` de PyInstaller sous macOS.

---

## CI multi-plateforme

`.github/workflows/build.yml` — déclenché sur tag `v*` ou manuellement.
Matrice : `windows-latest` · `macos-14` (Apple Silicon).
Sur tag, une **Release GitHub** est créée avec les artefacts (`if: always()`).

> **macOS Intel n'est PAS buildé en CI** : les runners `macos-13` de GitHub sont
> trop souvent saturés et bloquaient la Release. → builder l'Intel **en local**
> sur un Mac Intel (section ci-dessus).

> Les builds CI sont **sans le modèle** (exclu du dépôt) → onglet Classification
> inactif. Seul un build local avec `assets/` peuplé embarque le tri auto.

---

## Architecture

```
core/                      moteur pur, AUCUNE dépendance UI
  grading.py               algo v3 + anti-surexpo + profil série + default_workers()
  renaming.py              rename_folder, collect_rename_targets
  classification.py        zero-shot CLIP (preprocess cv2, Classifier onnxruntime,
                           run_classify_batch, manifest, tri physique)
  runner.py                run_grade_batch (pool multiprocessing + callbacks)
  config.py                persistance JSON (%APPDATA%/StudioPhoto/)
ui/                        PySide6 — style 100% via ui/style.py (QSS), zéro inline
  app.py                   MainWindow (sidebar 4 vues, progress card, console)
  grade_panel.py           onglet Étalonnage
  compare_panel.py         onglet Aperçu (slider avant/après)
  classify_panel.py        onglet Classification
  rename_panel.py          onglet Renommage
  workers.py               GradeWorker / RenameWorker / ClassifyWorker (QThread)
  style.py                 thème dark pro (palette ambre)
tools/
  export_clip_assets.py    génération hors-ligne des assets (torch, DEV only)
cli.py                     CLI grade / rename / classify / benchmark
build.py / build.bat       packaging PyInstaller (onedir/onefile)
make_ico.py                app_icon.png -> app_icon.ico carré multi-résolution
version.py                 source unique de la version
ui_entry.py                point d'entrée (freeze_support + QApplication + icône)
assets/                    modèle CLIP (local, gitignored) + README
tests/                     pytest
```

---

## Performances étalonnage (i7-8700, 6c/12t, 32 Go)

| Workers | ~débit |
|---------|--------|
| 1 | ~0.3 img/s |
| 4 (≈ défaut adaptatif) | ~1.2 img/s |
| 6 | ~1.8 img/s |
| 8 | ~1.9 img/s |

`default_workers()` = `ceil(cœurs_physiques × 0.6)`. Au-delà de 6, gain marginal
(goulot mémoire/IO sur images ~20 Mo). Mesurer : `python cli.py benchmark`.
