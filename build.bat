@echo off
REM Se place dans le dossier du script, quel que soit l'endroit d'où il est lancé
cd /d "%~dp0"

REM Pré-requis : pip install pyinstaller PySide6 Pillow numpy psutil

REM Conversion de l'icône si nécessaire
if exist app_icon.png (
    if not exist app_icon.ico (
        echo Conversion de l'icone PNG -^> ICO...
        python make_ico.py
    )
)

REM Build PyInstaller
if exist app_icon.ico (
    python -m PyInstaller ^
      --onefile ^
      --windowed ^
      --name "StudioPhoto" ^
      --icon app_icon.ico ^
      --add-data "core;core" ^
      --add-data "ui;ui" ^
      --add-data "app_icon.ico;." ^
      ui_entry.py
) else (
    echo Attention: app_icon.ico absent, build sans icone personnalisee.
    python -m PyInstaller ^
      --onefile ^
      --windowed ^
      --name "StudioPhoto" ^
      --add-data "core;core" ^
      --add-data "ui;ui" ^
      ui_entry.py
)

echo.
echo Build termine : dist\StudioPhoto.exe
pause
