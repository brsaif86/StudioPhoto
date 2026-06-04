"""
ui_entry.py — Point d'entrée de l'application graphique
========================================================
multiprocessing.freeze_support() DOIT être appelé avant tout import lourd
pour que l'exécutable PyInstaller --onefile fonctionne sous Windows.
"""

import multiprocessing as mp
import sys
from pathlib import Path

if __name__ == "__main__":
    mp.freeze_support()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from ui.app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("StudioPhoto")
    app.setOrganizationName("StudioPhoto")

    # Icône application (PNG ou ICO selon ce qui est disponible)
    _base = Path(__file__).parent
    for _icon_name in ("app_icon.ico", "app_icon.png"):
        _icon_path = _base / _icon_name
        if _icon_path.exists():
            app.setWindowIcon(QIcon(str(_icon_path)))
            break

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
