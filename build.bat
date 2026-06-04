@echo off
REM Se place dans le dossier du script, quel que soit l'endroit d'où il est lancé
cd /d "%~dp0"

REM Pré-requis : pip install pyinstaller PySide6 Pillow numpy psutil

REM Lecture de la version depuis version.py
for /f "delims=" %%v in ('python -c "from version import __version__; print(__version__)"') do set VERSION=%%v
set EXE_NAME=StudioPhoto-%VERSION%
echo Version detectee : %VERSION%

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
      --name "%EXE_NAME%" ^
      --icon app_icon.ico ^
      --add-data "core;core" ^
      --add-data "ui;ui" ^
      --add-data "version.py;." ^
      --add-data "app_icon.ico;." ^
      ui_entry.py
) else (
    echo Attention: app_icon.ico absent, build sans icone personnalisee.
    python -m PyInstaller ^
      --onefile ^
      --windowed ^
      --name "%EXE_NAME%" ^
      --add-data "core;core" ^
      --add-data "ui;ui" ^
      --add-data "version.py;." ^
      ui_entry.py
)

echo.
echo Build termine : dist\%EXE_NAME%.exe
pause
