"""
ui/style.py — QSS stylesheet v2.1
"""

ACCENT   = "#C8A96E"
BG0      = "#0D0D0D"
BG1      = "#131313"
BG2      = "#1A1A1A"
BG3      = "#222222"
BORDER   = "#2C2C2C"
TEXT1    = "#EBEBEB"
TEXT2    = "#888888"
TEXT3    = "#444444"
SUCCESS  = "#6BAE82"
ERROR    = "#AE6B6B"
SKIP     = "#555555"
REVIEW   = "#C8924E"   # orange/ambre — catégorie « À revoir »

QSS = f"""

/* ── Base ──────────────────────────────────────────────── */
* {{
    font-family: "Segoe UI", "SF Pro Text", sans-serif;
    font-size: 13px;
    color: {TEXT1};
    background-color: transparent;
}}

QMainWindow {{
    background-color: {BG0};
}}

QWidget {{
    background-color: transparent;
}}

/* ── Sidebar ────────────────────────────────────────────── */
QWidget#sidebar {{
    background-color: {BG1};
    border-right: 1px solid {BORDER};
}}

QLabel#app_logo {{
    color: {TEXT1};
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 3px;
    background: transparent;
}}

QLabel#app_version {{
    color: {TEXT3};
    font-size: 10px;
    letter-spacing: 2px;
    background: transparent;
}}

/* ── Nav buttons ────────────────────────────────────────── */
QPushButton#nav_grade,
QPushButton#nav_compare,
QPushButton#nav_classify,
QPushButton#nav_rename {{
    background: transparent;
    color: {TEXT2};
    border: none;
    border-left: 2px solid transparent;
    padding: 13px 20px;
    text-align: left;
    font-size: 11px;
    letter-spacing: 2px;
    font-weight: 600;
}}

QPushButton#nav_grade:checked,
QPushButton#nav_compare:checked,
QPushButton#nav_classify:checked,
QPushButton#nav_rename:checked {{
    color: {ACCENT};
    border-left: 2px solid {ACCENT};
    background-color: rgba(200,169,110,0.07);
}}

QPushButton#nav_grade:hover:!checked,
QPushButton#nav_compare:hover:!checked,
QPushButton#nav_classify:hover:!checked,
QPushButton#nav_rename:hover:!checked {{
    color: {TEXT1};
    background-color: {BG2};
    border-left: 2px solid {BORDER};
}}

/* ── Stats sidebar ──────────────────────────────────────── */
QLabel#stat_value {{
    color: {TEXT1};
    font-size: 20px;
    font-weight: 300;
    background: transparent;
}}

QLabel#stat_label {{
    color: {TEXT3};
    font-size: 9px;
    letter-spacing: 1.5px;
    background: transparent;
}}

/* ── Content area ────────────────────────────────────────── */
QWidget#content_area {{
    background-color: {BG0};
}}

/* ── Group boxes ─────────────────────────────────────────── */
QGroupBox {{
    background-color: {BG2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 22px;
    padding: 20px 16px 16px 16px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    top: -10px;
    padding: 2px 8px;
    background-color: {BG2};
    color: {TEXT3};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
}}

/* ── Inputs ──────────────────────────────────────────────── */
QLineEdit {{
    background-color: {BG3};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 8px 10px;
    color: {TEXT1};
    font-size: 12px;
    selection-background-color: {ACCENT};
    selection-color: #000;
}}

QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}

QLineEdit:disabled {{
    color: {TEXT3};
    border-color: #1E1E1E;
}}

QSpinBox {{
    background-color: {BG3};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 8px;
    color: {TEXT1};
    font-size: 12px;
    min-width: 64px;
}}

QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG3};
    border: none;
    width: 20px;
    border-radius: 0px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: #2E2E2E;
}}

QSpinBox::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {TEXT2};
    width: 0; height: 0;
}}

QSpinBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT2};
    width: 0; height: 0;
}}

/* ── Checkboxes ──────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT2};
    font-size: 12px;
    spacing: 10px;
    background: transparent;
}}

QCheckBox:hover {{
    color: {TEXT1};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background-color: {BG3};
}}

QCheckBox::indicator:hover {{
    border-color: {TEXT2};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* Simulation coche via border trick */
QCheckBox::indicator:checked {{
    image: none;
}}

/* ── Labels ──────────────────────────────────────────────── */
QLabel {{
    background: transparent;
}}

QLabel#form_label {{
    color: {TEXT2};
    font-size: 11px;
    letter-spacing: 0.5px;
    min-width: 80px;
}}

QLabel#progress_folder {{
    color: {ACCENT};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}

QLabel#progress_file {{
    color: {TEXT2};
    font-size: 11px;
    background: transparent;
}}

QLabel#hint_label {{
    color: {TEXT3};
    font-size: 11px;
    line-height: 1.5;
    background: transparent;
}}

/* ── Buttons ─────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG3};
    color: {TEXT1};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 14px;
    font-size: 12px;
}}

QPushButton:hover {{
    background-color: #2C2C2C;
    border-color: #3A3A3A;
}}

QPushButton:pressed {{
    background-color: {BG1};
}}

/* ── LANCER ─────────────────────────────────────────────── */
QPushButton#btn_run {{
    background-color: {ACCENT};
    color: #0D0D0D;
    border: none;
    border-radius: 5px;
    padding: 10px 32px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
    min-width: 120px;
    min-height: 38px;
}}

QPushButton#btn_run:hover {{
    background-color: #D4B87A;
}}

QPushButton#btn_run:pressed {{
    background-color: #B8976A;
}}

QPushButton#btn_run:disabled {{
    background-color: #2E2820;
    color: #504030;
    border: 1px solid #3A3020;
}}

/* ── ANNULER ─────────────────────────────────────────────── */
QPushButton#btn_cancel {{
    background-color: transparent;
    color: {TEXT3};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 10px 20px;
    font-size: 12px;
    min-height: 38px;
}}

QPushButton#btn_cancel:hover:enabled {{
    color: {ERROR};
    border-color: {ERROR};
    background-color: rgba(174,107,107,0.08);
}}

QPushButton#btn_cancel:disabled {{
    color: {TEXT3};
    border-color: #1E1E1E;
}}

/* ── Browse ──────────────────────────────────────────────── */
QPushButton#btn_browse {{
    background-color: transparent;
    color: {TEXT2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 14px;
    font-size: 11px;
    min-width: 88px;
}}

QPushButton#btn_browse:hover {{
    color: {TEXT1};
    border-color: {ACCENT};
    background-color: rgba(200,169,110,0.05);
}}

QPushButton#btn_browse:checked {{
    background-color: rgba(200,169,110,0.16);
    color: {ACCENT};
    border: 1px solid {ACCENT};
}}

QPushButton#btn_browse:disabled {{
    color: {TEXT3};
    border-color: #1E1E1E;
}}

/* ── ComboBox (mes presets) ──────────────────────────────── */
QComboBox {{
    background-color: {BG3};
    color: {TEXT1};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 11px;
}}

QComboBox:hover {{ border-color: #3A3A3A; }}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT2};
}}

QComboBox QAbstractItemView {{
    background-color: {BG2};
    color: {TEXT1};
    border: 1px solid {BORDER};
    selection-background-color: rgba(200,169,110,0.20);
    outline: none;
}}

/* ── Action bar ──────────────────────────────────────────── */
QWidget#action_bar {{
    background-color: #0F0F0F;
    border-top: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    min-height: 62px;
    max-height: 62px;
}}

/* ── Progress card ───────────────────────────────────────── */
QWidget#progress_card {{
    background-color: {BG2};
    border-bottom: 1px solid {BORDER};
}}

/* ── Progress bar ────────────────────────────────────────── */
QProgressBar#progress_bar {{
    background-color: {BORDER};
    border: none;
    border-radius: 1px;
    max-height: 2px;
    min-height: 2px;
    text-align: left;
}}

QProgressBar#progress_bar::chunk {{
    background-color: {ACCENT};
    border-radius: 1px;
}}

/* ── Console ─────────────────────────────────────────────── */
QTextEdit#console {{
    background-color: {BG1};
    border: none;
    border-top: 1px solid {BORDER};
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 10px 14px;
    color: {TEXT2};
}}

/* ── Scrollbar ───────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 5px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {BG3};
    border-radius: 2px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT3};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}

QScrollBar:horizontal {{
    height: 5px;
    background: transparent;
}}

QScrollBar::handle:horizontal {{
    background: {BG3};
    border-radius: 2px;
}}

/* ── Separator ───────────────────────────────────────────── */
QFrame#hline {{
    background-color: {BORDER};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* ── Éditeur v3 (presets + corrections) ──────────────────── */
QWidget#editor_col {{
    background: transparent;
}}

QFrame#editor_box {{
    background-color: {BG2};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

QLabel#editor_title {{
    color: {TEXT2};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}

QLabel#slider_value {{
    color: {ACCENT};
    font-size: 11px;
    font-weight: 600;
    min-width: 34px;
}}

QPushButton#preset_btn {{
    background-color: {BG3};
    color: {TEXT2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 8px 6px;
    font-size: 11px;
}}

QPushButton#preset_btn:hover {{
    color: {TEXT1};
    border-color: #3A3A3A;
}}

QPushButton#preset_btn:checked {{
    background-color: rgba(200,169,110,0.14);
    color: {ACCENT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}

/* curseurs d'édition (-100..100) */
QSlider::groove:horizontal {{
    height: 3px;
    background: {BG3};
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background: #D4B87A;
}}

/* groove neutre (pas de remplissage directionnel) : la poignée seule
   indique la valeur → curseur bipolaire « centré » sur 0. */
QSlider::sub-page:horizontal {{
    background: {BG3};
    border-radius: 1px;
}}
QSlider::add-page:horizontal {{
    background: {BG3};
    border-radius: 1px;
}}

/* ── Tooltip ─────────────────────────────────────────────── */
QToolTip {{
    background-color: {BG2};
    color: {TEXT1};
    border: 1px solid {BORDER};
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 11px;
}}
"""
