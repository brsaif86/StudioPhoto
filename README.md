# Studio Photo — Étalonnage & Renommage

Application Windows autonome regroupant deux outils photo :
1. **Étalonnage adaptatif v3** — couleur + N&B, multiprocessing, reprise de lot.
2. **Renommage séquentiel** — par dossier, two-pass, dry-run, reprise.

---

## Prérequis développeur

- Python 3.11+
- `pip install -r requirements.txt`

```
pip install Pillow numpy PySide6 pyinstaller pytest
```

---

## Lancer l'application

```bat
python ui_entry.py
```

---

## Utilisation CLI

```bat
# Étalonnage d'un dossier (récursif, 6 processus par défaut)
python cli.py grade C:\Photos\Mariage

# Avec options
python cli.py grade C:\Photos --workers 8 --output C:\Photos_graded --suffix _edit

# Renommage en aperçu (dry-run)
python cli.py rename C:\Photos

# Renommage réel
python cli.py rename C:\Photos --real

# Benchmark 6 vs 8 processus sur 20 images
python cli.py benchmark C:\Photos --workers 6 8 --sample 20
```

---

## Tests

```bat
pytest tests/ -v
```

La première exécution de `test_regression_color_grade` génère l'image de référence `tests/ref_color_grade.png`.
Les suivantes comparent la sortie pixel-à-pixel (tolérance RMSE < 2/255).

---

## Build .exe

```bat
build.bat
```

L'exécutable `dist\StudioPhoto.exe` est autonome (aucun Python requis).
Double-clic pour lancer. Le multiprocessing fonctionne grâce à `freeze_support()`.

---

## Architecture

```
core/
  grading.py     — algorithme v3 (is_grayscale, analyze_image, apply_color_grade,
                   apply_bw_grade, process_image, _grade_worker, collect_grade_tasks)
  renaming.py    — rename_folder, collect_rename_targets
  runner.py      — run_grade_batch (pool multiprocessing + callbacks)
  config.py      — persistance JSON des réglages (%APPDATA%/StudioPhoto/)
ui/
  app.py         — MainWindow PySide6
  grade_panel.py — onglet Étalonnage
  rename_panel.py— onglet Renommage
  workers.py     — GradeWorker / RenameWorker (QThread)
cli.py           — CLI grade / rename / benchmark
ui_entry.py      — point d'entrée (freeze_support + QApplication)
tests/
  test_grading.py
  test_renaming.py
```

---

## Performances (i7-8700, 6c/12t, 32 Go)

| Workers | ~débit mesuré |
|---------|--------------|
| 1       | ~0.3 img/s   |
| 4       | ~1.2 img/s   |
| **6**   | **~1.8 img/s** ← défaut |
| 8       | ~1.9 img/s   |
| 12      | ~1.9 img/s   |

Au-delà de 6 workers le gain est marginal (goulot mémoire/IO sur images 20 Mo).
Utilise `python cli.py benchmark` pour mesurer sur ta machine.
