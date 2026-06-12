# StudioPhoto — Document de référence du projet

> Référence complète de la conversation de développement.
> Repo : https://github.com/brsaif86/StudioPhoto
> Machine cible : Intel i7-8700 (6c/12t) · 32 Go RAM · Windows 11 · GTX 1050 2 Go

---

## 1. Objectif initial

Transformer des scripts Python existants (étalonnage + renommage photo) en une
**application Windows native, rapide et fiable**, packagée en `.exe` autonome
(double-clic, sans Python installé).

Deux outils regroupés :
1. **Étalonnage** (grading) adaptatif v3 — couleur + N&B
2. **Renommage** séquentiel des images par dossier

---

## 2. Code source d'origine (point de départ)

| Fichier | Rôle |
|---------|------|
| `photo_tools_gui.py` | App Tkinter — **logique de référence v3** (à conserver) |
| `grade_v3.py` | Version CLI de l'étalonnage adaptatif |
| `grade.py`, `grade_v2.py` | Versions antérieures (historique) |
| `rename_images.py` | Logique de renommage d'origine |

**Règle d'or** : le résultat visuel de l'étalonnage doit rester **identique** à
l'algorithme v3. Ne pas changer les coefficients sans demande explicite.

### Algorithme v3 (résumé)
Analyse de chaque image puis traitement adaptatif :
- **Métriques** : luminosité moyenne, contraste (écart-type), dominante chaude
  (R−B), ratio de hautes lumières
- **Étapes couleur** : balance des blancs → shadow lift → S-curve → correction
  peau (masque orange flouté) → désaturation légère → gamma lift → neutralisation
  des blancs
- **N&B** : détecté séparément, traité avec lift + S-curve doux uniquement
- Tous les seuils s'adaptent aux métriques de l'image

---

## 3. Architecture finale

```
StudioPhoto/
├── core/                    # Moteur pur — AUCUNE dépendance UI
│   ├── grading.py           # Algo v3 : is_grayscale, analyze_image,
│   │                        #   apply_color_grade, apply_bw_grade,
│   │                        #   process_image, _grade_worker (picklable),
│   │                        #   collect_grade_tasks, default_workers()
│   ├── renaming.py          # rename_folder, collect_rename_targets
│   ├── runner.py            # run_grade_batch (Pool mp + callbacks riches)
│   └── config.py            # Persistance JSON %APPDATA%/StudioPhoto/
├── ui/                      # Couche graphique PySide6 (appelle le core)
│   ├── app.py               # MainWindow v2 (sidebar, progress card, console)
│   ├── grade_panel.py       # Onglet Étalonnage
│   ├── rename_panel.py      # Onglet Renommage
│   ├── workers.py           # GradeWorker / RenameWorker (QThread + signaux)
│   └── style.py             # QSS — thème dark professionnel
├── tests/
│   ├── test_grading.py      # 16 tests (dont régression pixel)
│   ├── test_renaming.py     # 9 tests
│   └── ref_color_grade.png  # Image de référence pour le test de non-régression
├── cli.py                   # CLI : grade / rename / benchmark
├── ui_entry.py              # Point d'entrée (freeze_support + QApplication + icône)
├── version.py               # Source unique de vérité (__version__ = "1.0.2")
├── make_ico.py              # Convertit app_icon.png → app_icon.ico
├── build.bat                # Build PyInstaller local
├── app_icon.png / .ico      # Icône application
├── requirements.txt
├── README.md
└── .github/workflows/build.yml  # CI multi-plateforme
```

**Principe imposé** : séparation stricte `core/` (testable seul) ↔ `ui/`.
Les workers multiprocessing sont **au niveau module** (picklables — exigence
Windows spawn).

---

## 4. Décisions techniques clés

### Performance / Workers
- **`default_workers()`** dans `core/grading.py` :
  ```python
  import psutil
  physical = psutil.cpu_count(logical=False)  # cœurs physiques réels
  return max(1, math.ceil(physical * 0.6))    # 60 % des cœurs physiques
  ```
- Repli `os.cpu_count() // 2` si `psutil` absent.
- **i7-8700 (6 cœurs physiques) → 4 workers** par défaut.
- S'adapte à toute machine. Configurable 1–64 dans l'UI.
- Raison : grading limité par calcul + bande passante mémoire ;
  l'hyperthreading n'apporte rien. 60 % laisse des ressources au système.

### Mémoire
- Une seule conversion NumPy par image.
- Opérations en place (`*=`, `+=`, `np.clip(..., out=...)`, `**=`).
- Libération explicite (`del`) après sauvegarde.

### Multiprocessing Windows (pièges évités)
- `multiprocessing.freeze_support()` en **tout premier** dans `ui_entry.py`
  et `cli.py` (sinon l'`.exe --onefile` relance la fenêtre en boucle).
- Workers au niveau module (picklables).
- Aucun objet UI passé aux workers — uniquement chemins/chaînes.
- `pathlib` partout (espaces, accents, chemins Windows).
- `rename_images.py` exécutait du code au niveau module → **non reproduit**.

---

## 5. Fonctionnalités

### Étalonnage
- Dossier source ; sortie optionnelle (vide = `_output` par dossier)
- Suffixe configurable (`_graded`)
- Mode récursif
- Skip des images déjà traitées (reprise de lot)
- Exclut `._*` (macOS) et le dossier `_output`
- JPEG `quality=95, subsampling=0` (qualité paramétrable 60–100)
- Détection auto N&B vs couleur

### Renommage
- Chaque sous-dossier → `<nom_dossier>_001.ext`, `_002`, …
- Reprise intelligente (repère les fichiers déjà nommés, continue sans trou)
- **Deux passes** (noms temporaires) — anti-collision Windows
- **Dry-run** (aperçu sans modification)
- **Confirmation explicite** avant renommage réel
- Détection + signalement des trous de séquence

### CLI (`cli.py`)
```bash
python cli.py grade <dossier> --workers 6 --output <dir> --suffix _edit
python cli.py rename <dossier>            # dry-run par défaut
python cli.py rename <dossier> --real     # renommage réel
python cli.py benchmark <dossier> --workers 6 8 --sample 20  # débit img/s
```

---

## 6. Interface graphique — évolution

### v1 (Tkinter → PySide6 basique)
- Onglets, console, barre de progression, bouton annuler.

### v2 (design dark professionnel — Capture One × DaVinci Resolve)
- **`ui/style.py`** : QSS complet, palette ambre `#C8A96E` sur fond `#0D0D0D`
- **Sidebar** de navigation (Étalonnage / Renommage) + stats en bas
  (Traitées / Ignorées / Erreurs)
- **Carte de progression** riche :
  - Dossier courant (en ambre)
  - Fichier courant
  - Compteur `X / Y` + pourcentage
  - **Vitesse** (img/s) — moyenne glissante sur 10 images
  - **ETA** (mm:ss) — temps restant estimé
  - Barre fine 2px
- **Log coloré** : vert ✓ · rouge ✗ · gris ⏭ (via `QTextCharFormat`)

### v2.1 (corrections accessibilité / layout)
- Suppression des `setStyleSheet()` **inline** (ils écrasaient le QSS et
  cachaient le bouton LANCER)
- `QScrollArea` sur le contenu → group box jamais coupée
- `QGroupBox` `margin-top: 22px` + titre `top: -10px` → titre toujours visible
- Checkboxes : carré ambre plein (le `::after` n'est pas supporté en QSS Qt)
- `QGridLayout` propre, labels alignés à droite
- Couleurs des labels via `objectName` QSS, plus en inline

### Signaux enrichis (core → UI)
`run_grade_batch` expose des callbacks :
`on_log`, `on_progress(done, total)`, `on_current(folder, file)`,
`on_speed(img/s)`, `on_eta(sec)`. Les `QThread` les relaient via signaux Qt.

---

## 7. Versioning

- **`version.py`** = source unique de vérité (`__version__ = "1.0.2"`).
- Le titre de la fenêtre, le nom de l'exe et les artefacts CI en découlent.
- Pour publier une nouvelle version : modifier `version.py`, tout suit.

| Élément | Forme |
|---------|-------|
| Titre fenêtre | `StudioPhoto v1.0.2 — Étalonnage & Renommage` |
| Exe local | `StudioPhoto-1.0.2.exe` |
| Artefact Windows | `StudioPhoto-1.0.2-windows-x86_64.exe` |
| Artefact macOS Intel | `StudioPhoto-1.0.2-macos-intel` |
| Artefact macOS Silicon | `StudioPhoto-1.0.2-macos-silicon` |

---

## 8. Icône

- Source : `app_icon.png` (1024×1024, objectif + nuancier + étiquette A→Z)
- `make_ico.py` → `app_icon.ico` multi-résolution (16→256 px)
- Chargée au démarrage via `QIcon` dans `ui_entry.py`
- Embarquée dans l'exe (`--icon app_icon.ico --add-data app_icon.ico:.`)

---

## 9. Packaging

### Build local Windows
```bat
build.bat
```
- `cd /d "%~dp0"` en tête (évite l'erreur PyInstaller depuis System32)
- `python -m PyInstaller` (résout le PATH manquant)
- Convertit l'icône PNG→ICO si nécessaire
- Sortie : `dist\StudioPhoto-<version>.exe` (~68 Mo, autonome)

### Commande PyInstaller de référence
```bat
python -m PyInstaller --onefile --windowed --name "StudioPhoto" ^
  --icon app_icon.ico ^
  --add-data "core;core" --add-data "ui;ui" ^
  --add-data "version.py;." --add-data "app_icon.ico;." ^
  ui_entry.py
```

### CI multi-plateforme — `.github/workflows/build.yml`
Déclenché sur tag `v*` ou `workflow_dispatch`. Matrice :

| Runner | Cible | Statut |
|--------|-------|--------|
| `windows-latest` | x86_64 | ✅ fiable |
| `macos-14` | Apple Silicon arm64 | ✅ fiable |
| `macos-13` | Intel x86_64 | ⚠ runners souvent saturés |

Sur tag `v*` → Release GitHub automatique avec les artefacts.

---

## 10. Tests & critères d'acceptation

```bat
pytest tests/ -v        # 25 tests
```

- [x] **Non-régression** : `test_regression_color_grade` compare la sortie
      pixel-à-pixel à `ref_color_grade.png` (RMSE < 2/255)
- [x] **Skip** fonctionne (2e passage ne retraite pas)
- [x] **Renommage 2 passes** sans perte ; dry-run inerte ; reprise correcte
- [x] **UI réactive** pendant un lot ; annulation propre
- [x] **Benchmark** affiche le débit img/s
- [x] **Exe packagé** se lance au double-clic
- [x] **Image corrompue** → erreur isolée et journalisée (pas de crash du lot)

---

## 11. Problèmes rencontrés & solutions (CI)

| Problème | Cause | Solution |
|----------|-------|----------|
| Build macOS Silicon échoue | `--target-arch universal2` ; PySide6 pas universal2 sur macos-14 | Build natif par arch (suppression de `universal2`) |
| `--add-data core;core` casse sur Windows | `;` = séparateur de commandes PowerShell | Tableau d'args PowerShell `@args` + séparateur `:` (PyInstaller 6+) |
| `pyinstaller` non reconnu | Pas dans le PATH | `python -m PyInstaller` |
| Erreur « run from System32 » | build.bat lancé hors dossier | `cd /d "%~dp0"` en tête |
| `macos-13` bloqué en queue (>20 min) | Runners Intel GitHub saturés | `timeout-minutes: 30` + `continue-on-error: true` sur ce job seul |
| Bouton LANCER invisible (v2) | `setStyleSheet()` inline écrasait le QSS | Tout le style dans `ui/style.py` via `objectName` |
| Group box coupée en haut (v2) | margin + pas de scroll | `QScrollArea` + `margin-top: 22px` |

> Note : le `timeout-minutes` ne s'applique qu'une fois le runner **assigné** —
> un job bloqué en *queue* peut attendre indéfiniment (limite GitHub).

---

## 12. Workflow Git du projet

- Branche par défaut : `master`
- Branche `main` créée au commit initial → PR `master → main` pour la revue
- PR ouvertes : #1 (fix CI), #2 (workers adaptatifs + icône + version + UI v2)
- Tags : `v1.0.0`, `v1.0.1` (déclenchent les builds CI)

### Commandes utiles
```bash
# Déclencher un build manuellement
gh workflow run build.yml --repo brsaif86/StudioPhoto --ref master

# Annuler un run bloqué
gh run cancel <run_id> --repo brsaif86/StudioPhoto

# Publier une release (build + artefacts auto)
git tag v1.0.x && git push origin v1.0.x
```

> `gh` installé dans `C:\Program Files\GitHub CLI\gh.exe` (pas dans le PATH).

---

## 13. Préférences utilisateur retenues

- **Setup local : 6 processus** forcés via la config persistée
  (`%APPDATA%\StudioPhoto\settings.json` → `grade_workers: 6`).
  La config locale prime toujours sur `default_workers()` (4 sur cette machine).
- Communication en **français**.
- Design **épuré**, inspiré des apps de traitement d'image professionnelles.

---

## 14. Dépendances

**Runtime** (`requirements.txt`, embarquées dans l'exe) :
```
Pillow>=10.0              # I/O image + flous gaussiens (grading)
numpy>=1.26              # calcul matriciel
PySide6>=6.6            # UI Qt
psutil>=5.9            # détection cœurs physiques
opencv-python-headless # décodage/prétraitement + classification
onnxruntime>=1.17     # inférence CLIP (ONNX) — PAS de torch au runtime
pyinstaller>=6.0     # packaging
pytest>=8.0         # tests
```

**Dev uniquement** (`requirements-dev.txt`, jamais dans l'exe) :
```
torch  open_clip_torch  onnx  onnxscript   # export des assets CLIP
```

---

## 15. Évolutions post-1.0

### v1.1.0 — Corrections issues des retours client (PDF)
Retours retouche extraits du PDF client (lecture via PyMuPDF, pages = images) :
- **Blancs neutres** (étape 7 réécrite) : la robe blanche ne vire plus au bleu.
  Neutralisation pondérée par luminance, rampe 0.72→0.92. Test `test_whites_stay_neutral`.
- **Anti-surexposition** : shadow lift coupé sur images claires + rolloff des
  hautes lumières (étape 6b). Test `test_bright_image_not_overexposed`.
- **Mode série cohérente** (`compute_folder_profile`) : profil moyen par dossier
  appliqué à toute la série → rendu uniforme. **Activé par défaut** (config, UI, CLI).
- Régression pixel (ton moyen) **inchangée** : les correctifs ne touchent que les
  hautes lumières.

### v1.2.0 — Onglet Aperçu + Classification
- **Aperçu** (`ui/compare_panel.py`) : comparateur avant/après à curseur,
  `grade_preview()` en mémoire (rendu fidèle au lot), QThread.
- **Classification / tri auto** (`core/classification.py`) — **2 moteurs**,
  dispatcher `_make_classifier` (défaut Few-shot, repli zero-shot) :
  - **Few-shot** (`core/fewshot.py`, défaut) : apprend des dossiers **déjà triés**
    (un sous-dossier = une catégorie). Embeddings **SigLIP** L2 + **régression
    logistique multinomiale numpy** (aucune dépendance ajoutée). Entraînement en
    secondes, inférence en ms/photo, modèle dans `%APPDATA%/StudioPhoto/
    fewshot_model.npz`. Le plus fiable car il apprend la définition réelle des
    catégories du client. Multi-dossiers (cumule plusieurs mariages), noms
    normalisés (`01 Preparations`→`Preparations`), dossiers de sélection
    (highlights…) ignorés, plafond/classe. `FewShotTrainWorker` (UI, hors thread,
    annulable). Garde-fou : modèle d'un autre backbone (dim ≠) → repli zero-shot.
  - **Zero-shot SigLIP** (repli) : **cv2 + onnxruntime** (cv2.dnn ne sait pas
    exécuter les ViT). Similarité embeddings image/texte précalculés.
    `tools/export_clip_assets.py` (offline, torch) génère l'ONNX (`dynamo=False`,
    opset 14) + embeddings + meta ; lit la normalisation réelle du modèle (SigLIP
    `[0.5,0.5,0.5]`). Backbone par défaut **ViT-B-16-SigLIP-256/webli** (768-dim).
  - 6 classes + « À revoir » ; manifest json/csv (défaut) ou tri copie/déplacement.
  - Validé (CLIP) sur jeu client étiqueté : Ktuba 95 %, Dance 92 %, Love 88 %.

### Icône & packaging
- `make_ico.py` corrigé : recadre + carré + ICO multi-résolution (le PNG source
  1536×1024 était déformé).
- `build.bat` → `build.py` (robuste, fini les pièces cmd fragiles).
- **`--onedir` par défaut** quand le modèle est dans `assets/` (démarrage
  instantané, lanceur 5.9 Mo) ; `--onefile` sinon. `STUDIOPHOTO_ONEFILE=1` force.
- `--exclude-module torch …` : torch ne fuite plus dans l'exe.

### Build macOS
- **PyInstaller ne cross-compile pas** : Windows build Windows, Mac build Mac.
  Le binaire = arch de la machine (arm64 Silicon / x86_64 Intel).
- `build_mac.sh` : script clé en main (venv + deps + tests + `build.py`).
- README : section « Build macOS (Intel & Apple Silicon) » pas à pas + Gatekeeper
  (`xattr -dr com.apple.quarantine`).
- **macOS Intel retiré de la CI** : runners `macos-13` saturés bloquaient le job
  `release`. Build Intel = en local sur un Mac Intel. CI = Windows + Silicon,
  `release: if: always()`.

### Pièges Windows rencontrés (et corrigés)
| Symptôme | Cause | Fix |
|----------|-------|-----|
| `cv2.imread` renvoie None | chemins non-ASCII (hébreu/accents) | `np.fromfile` + `cv2.imdecode` |
| cv2.dnn `findCommonShape` assert | cv2.dnn n'exécute pas les ViT | backend onnxruntime |
| ONNX 1.2 Mo vide | exporteur dynamo (torch 2.12) | `dynamo=False` |
| Emoji ✅ crash export | console cp1252 | `PYTHONUTF8=1` |
| exe 961 Mo | torch embarqué par PyInstaller | `--exclude-module` |

---

## 16. Évolutions v2 / v3

### v2.0 — Refonte UI + corrections rendu
- Disposition **2 colonnes** (réglages | aperçu), puis aperçu intégré à
  l'étalonnage (curseur avant/après, navigation par image).
- Couleurs **moins fades** (désaturation 7→3 %), **peau plus naturelle**
  (correction peau adoucie).
- Fixes packaging : `cv2.imdecode` (chemins Unicode), flux `stdout/stderr`
  non-None en `--windowed` (multiprocessing), `--onedir` par défaut quand le
  modèle est embarqué, nettoyage `dist/` avant build (verrous).

### v3.0 — Éditeur interactif
- `core/adjustments.py` : `EditParams` (presets **empilables** + 12 curseurs),
  `render_with_profile`. Base Naturel (= v3) ou Noir & Blanc + looks créatifs.
  **Invariant** : Naturel + curseurs à 0 == v3 strict.
- Presets (jeu validé client) : **Naturel** · **Noir & Blanc** · **Cinématique**.
  Naturel répond à lui seul à toutes les exigences (couleurs naturelles, teint
  réaliste, série cohérente) ; Cinématique = touche ciné empilable.
- **Mes presets** (sauver/charger), **pipette balance des blancs**, réglage
  **global ou par image**, « Réinitialiser » = **photo originale**.
- UI : **onglets en haut** (sidebar supprimée), compteurs retirés, bas **50/50**
  (Dossiers+Options+LANCER | console), aperçu 60 % / éditeur 40 %, boutons compacts.

### v3.2 — Moteur LUT 3D
- `core/lut_engine.py` : LUT `.cube` (interp. trilinéaire vectorisée), vibrance,
  **cache module-level** (dossier+nom) → `.cube` lu une fois par worker.
- Intégrée au pipeline (étape 8, après neutralisation des blancs) **et** à
  l'éditeur (`render_with_profile`). Workers picklables (seules les chaînes
  `lut_dir`/`lut_name` passent ; `LutEngine` reconstruit dans le worker).
- **Bugs corrigés à la revue** : inversion R↔B (`.cube` rouge le plus rapide →
  `transpose(2,1,0,3)`) ; cache raté par image (lru_cache sur méthode →
  fonction module) ; LUT ignorée avec l'éditeur ; test de régression réécrit.

### v4.0 — Few-shot SigLIP-B, simplification (Ollama + LUT retirés)
- **Classification few-shot sur embeddings SigLIP** (backbone par défaut
  **ViT-B-16-256/webli**, 768-dim, léger/rapide). `export_clip_assets.py` lit la
  normalisation réelle du modèle (`[0.5,0.5,0.5]`). Few-shot multi-dossiers
  (cumule plusieurs mariages), noms normalisés, sélections (highlights) ignorées,
  plafond/classe. Garde-fou dim (≠ backbone) → repli zero-shot.
- **Ollama entièrement retiré** : trop lent (~s/photo) et peu fiable (~40 %) sur
  gros volumes. Le few-shot le remplace (rapide, ~ms/photo, apprend les catégories).
- **LUT 3D retirée** (moteur, UI « RENDU & LUT », LUT d'exemple, config) : pour un
  rendu maîtrisé sans surprise, on s'appuie sur les presets + curseurs manuels.
- **Presets mutuellement exclusifs** : un seul preset appliqué à la fois (Naturel /
  Noir & Blanc / Cinématique) → rendu cohérent et reproductible.
- **Fix UI** : titres de section (`QGroupBox`) qui étaient rognés par le cadre.

### v3.4 — Classification few-shot (apprend tes tris)
- `core/fewshot.py` : apprend des dossiers déjà triés (embeddings CLIP +
  régression logistique numpy) → rapide, 100 % local, bien plus fiable que le
  zero-shot/LLM sur une taxonomie subjective. Modèle dans `%APPDATA%`.
- UI : moteur **Few-shot** par défaut + section « APPRENTISSAGE » (dossier
  d'exemples + bouton Entraîner + état du modèle). `FewShotTrainWorker`,
  annulation coopérative, précision validation 85/15 affichée.

### v3.3 — LUT d'exemple + presets validés (+ tentative Ollama, retirée en 4.0)
- **6 LUT `.cube` d'exemple** (mariage/cinéma) générées par
  `tools/make_sample_luts.py` et embarquées dans `assets/luts/`.
- **Presets réduits au jeu validé client** : Naturel · Noir & Blanc · Cinématique
  (retrait des 5 autres looks). `apply_manual` suit l'**ordre pro** (lumière →
  balance des blancs → contraste → couleur → local → finitions).
- **Fix** : crash au démarrage de l'exe (`QComboBox`/`QSlider` non importés).

## 17. Versions

| Version | Apport |
|---------|--------|
| 1.0.x | App de base (étalonnage + renommage), CI multi-OS, icône, versioning |
| 1.1.0 | Anti-surexposition + série cohérente + blancs neutres (défaut) |
| 1.2.0 | Aperçu avant/après + Classification zero-shot CLIP |
| 2.0.0 | Aperçu intégré, peau naturelle, fixes packaging |
| 3.0.0 | Éditeur interactif (presets empilables, curseurs, pipette, UI onglets) |
| 3.2.0 | Moteur LUT 3D `.cube` + vibrance (revue & correctifs) |
| 3.3.0 | Classification hybride CLIP+Ollama + LUT d'exemple + presets validés |
| 3.4.0 | Classification **few-shot** (apprend les dossiers triés) — rapide & fiable |
| 4.0.0 | Few-shot **SigLIP-B** ; **Ollama + LUT retirés** ; presets exclusifs |
| 4.0.1 | Naturel = rendu v3 original validé client ; preset **Naturel 2** ; fix double-sélection |
| 4.2.0 | **Naturel 2 calibré** : couleurs fidèles + touche cinématique (teal & orange subtil) |

---

## 18. État actuel (v4.0.0)

- ✅ 3 onglets : Étalonnage (éditeur intégré) · Classification · Renommage
- ✅ `core/` pur testable seul ; **60 tests** au vert (régression pixel, éditeur, few-shot)
- ✅ Éditeur : **4 presets exclusifs** (Naturel v3, Naturel 2 chaud, N&B, Cinématique), 12 curseurs, pipette
- ✅ Classification : **2 moteurs** — Few-shot (défaut, apprend tes tris) + zero-shot SigLIP (repli)
- ✅ Backbone embeddings **SigLIP ViT-B-16-256** (768-dim, léger/rapide, normalisation lue auto)
- ✅ Few-shot multi-dossiers : cumule plusieurs mariages, normalise les noms, ignore les sélections
- ✅ **Ollama et LUT entièrement retirés** — rendu maîtrisé, 100 % cv2+numpy+onnxruntime
- ✅ Workers adaptatifs (60 % cœurs physiques), série cohérente par défaut
- ✅ CLI `grade` / `rename` / `classify` / `benchmark`
- ✅ UI dark pro, onglets en haut, style 100 % QSS (titres de section corrigés)
- ✅ Build Windows + macOS Silicon en CI (sur tag `v*`) ; build local 4.0.0 OK
- ⚠ macOS Intel = build local (retiré de la CI)
- ⚠ Exes CI sans modèle SigLIP (gitignored) ; à générer via export_clip_assets.py

---

*Document de référence — mis à jour jusqu'à la v4.0.0.*
