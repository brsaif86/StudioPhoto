"""
ui_entry.py — Point d'entrée de l'application graphique
========================================================
multiprocessing.freeze_support() DOIT être appelé avant tout import lourd
pour que l'exécutable PyInstaller --onefile fonctionne sous Windows.
"""

import multiprocessing as mp
import sys

if __name__ == "__main__":
    mp.freeze_support()

    from PySide6.QtWidgets import QApplication
    from ui.app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("StudioPhoto")
    app.setOrganizationName("StudioPhoto")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
