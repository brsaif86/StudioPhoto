@echo off
REM Lance le build via le script Python robuste (évite les pièges de cmd).
REM Double-clic possible : la fenêtre reste ouverte grâce à pause.
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python introuvable dans le PATH.
    echo Installe Python 3.11+ et coche "Add to PATH", puis relance.
    echo.
    pause
    exit /b 1
)

python build.py
set BUILD_RC=%errorlevel%

echo.
if "%BUILD_RC%"=="0" (
    echo Build termine avec succes.
) else (
    echo Le build a echoue (code %BUILD_RC%^).
)
echo.
pause
