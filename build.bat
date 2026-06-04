@echo off
REM Compile StudioPhoto en un .exe autonome Windows
REM Pré-requis : pip install pyinstaller PySide6 Pillow numpy

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "StudioPhoto" ^
  --add-data "core;core" ^
  --add-data "ui;ui" ^
  ui_entry.py

echo.
echo Build terminé. L'exécutable se trouve dans dist\StudioPhoto.exe
pause
