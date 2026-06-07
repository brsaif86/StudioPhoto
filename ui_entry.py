"""
ui_entry.py — Point d'entrée de l'application graphique
========================================================
multiprocessing.freeze_support() DOIT être appelé avant tout import lourd
pour que l'exécutable PyInstaller --onefile fonctionne sous Windows.
"""

import multiprocessing as mp
import sys
from pathlib import Path


# ── Garde-fou flux standard (PyInstaller --windowed) ──────────────────────────
# Dans un exe --windowed (sans console), sys.stdout/sys.stderr valent None.
# Les process enfants du Pool d'étalonnage plantent alors sur `None.write`
# (→ BrokenPipeError). On installe un flux nul valide. Ce code s'exécute au
# niveau module donc AUSSI dans les process enfants (qui réimportent le main).
class _NullStream:
    def write(self, *_args, **_kwargs):
        return 0
    def flush(self):
        pass
    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()


if __name__ == "__main__":
    mp.freeze_support()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from ui.app import MainWindow
    from version import APP_NAME, __version__

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)

    # Icône application — version carrée en priorité (ICO multi-résolution,
    # puis PNG carré généré), jamais le PNG source rectangulaire.
    # En .exe --onefile, les ressources sont extraites dans sys._MEIPASS.
    _base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    for _icon_name in ("app_icon.ico", "app_icon_square.png"):
        _icon_path = _base / _icon_name
        if _icon_path.exists():
            app.setWindowIcon(QIcon(str(_icon_path)))
            break

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
