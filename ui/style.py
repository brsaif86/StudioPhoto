"""
ui/style.py — QSS stylesheet v2
Aesthetic: dark professional photo tool (Capture One × DaVinci Resolve)
Palette: near-black bg · warm amber accent · muted greens/reds for status
"""

ACCENT   = "#C8A96E"   # amber gold
BG0      = "#0B0B0B"   # deepest bg
BG1      = "#111111"   # sidebar + panels
BG2      = "#181818"   # elevated surface
BG3      = "#202020"   # input bg / hover
BORDER   = "#272727"   # subtle separator
TEXT1    = "#E8E8E8"   # primary text
TEXT2    = "#888888"   # secondary / labels
TEXT3    = "#444444"   # disabled / placeholders
SUCCESS  = "#5A9E6F"   # muted green
ERROR    = "#9E5A5A"   # muted red
SKIP     = "#555555"   # skipped (gray)

QSS = f"""
/* ─── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {BG0};
    color: {TEXT1};
    font-family: "Segoe UI", "SF Pro Text", sans-serif;
    font-size: 13px;
}}

/* ─── Sidebar ────────────────────────────────────────────────────────────── */
#sidebar {{
    background-color: {BG1};
    border-right: 1px solid {BORDER};
    min-width: 180px;
    max-width: 180px;
}}

#app_logo {{
    color: {TEXT1};
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 24px 20px 8px 20px;
}}

#app_version {{
    color: {TEXT3};
    font-size: 10px;
    letter-spacing: 2px;
    padding: 0px 20px 24px 20px;
}}

/* ─── Nav Buttons ─────────────────────────────────────────────────────────── */
QPushButton#nav_grade, QPushButton#nav_rename {{
    background: transparent;
    color: {TEXT2};
    border: none;
    border-left: 2px solid transparent;
    padding: 14px 20px;
    text-align: left;
    font-size: 11px;
    letter-spacing: 1.5px;
    font-weight: 500;
}}

QPushButton#nav_grade:checked, QPushButton#nav_rename:checked {{
    color: {ACCENT};
    border-left: 2px solid {ACCENT};
    background-color: rgba(200, 169, 110, 0.06);
    font-weight: 600;
}}

QPushButton#nav_grade:hover:!checked, QPushButton#nav_rename:hover:!checked {{
    color: {TEXT1};
    background-color: {BG2};
    border-left: 2px solid {BORDER};
}}

/* ─── Group boxes / Sections ─────────────────────────────────────────────── */
QGroupBox {{
    background-color: {BG2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding: 16px 14px 14px 14px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.8px;
    color: {TEXT2};
    text-transform: uppercase;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: -6px;
    padding: 0 6px;
    background-color: {BG2};
    color: {TEXT2};
}}

/* ─── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {BG3};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 10px;
    color: {TEXT1};
    font-size: 12px;
    selection-background-color: {ACCENT};
}}

QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background-color: #1C1C1C;
}}

QLineEdit::placeholder {{
    color: {TEXT3};
}}

QSpinBox {{
    background-color: {BG3};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 8px;
    color: {TEXT1};
    font-size: 12px;
}}

QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background: {BG3};
    border: none;
    width: 18px;
}}

QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {TEXT2};
}}

QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT2};
}}

/* ─── Checkboxes ──────────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT2};
    font-size: 12px;
    spacing: 8px;
}}

QCheckBox:hover {{
    color: {TEXT1};
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG3};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    image: none;
}}

QCheckBox::indicator:checked::after {{
    content: "✓";
}}

/* ─── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG3};
    color: {TEXT1};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 16px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: #2A2A2A;
    border-color: #3A3A3A;
}}

QPushButton:pressed {{
    background-color: #141414;
}}

QPushButton#btn_run {{
    background-color: {ACCENT};
    color: #0B0B0B;
    border: none;
    border-radius: 4px;
    padding: 9px 28px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QPushButton#btn_run:hover {{
    background-color: #D9BC82;
}}

QPushButton#btn_run:pressed {{
    background-color: #B8986A;
}}

QPushButton#btn_run:disabled {{
    background-color: #2A2420;
    color: {TEXT3};
}}

QPushButton#btn_cancel {{
    background-color: transparent;
    color: {TEXT2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 9px 18px;
    font-size: 12px;
}}

QPushButton#btn_cancel:hover {{
    background-color: #1E1414;
    color: {ERROR};
    border-color: {ERROR};
}}

QPushButton#btn_cancel:disabled {{
    color: {TEXT3};
    border-color: {TEXT3};
}}

QPushButton#btn_browse {{
    background-color: transparent;
    color: {TEXT2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 11px;
    min-width: 80px;
}}

QPushButton#btn_browse:hover {{
    color: {TEXT1};
    border-color: {ACCENT};
    background-color: rgba(200, 169, 110, 0.06);
}}

/* ─── Progress Bar ────────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {BG3};
    border: none;
    border-radius: 2px;
    height: 3px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 2px;
}}

#progress_thin {{
    background-color: {BORDER};
    border: none;
    border-radius: 1px;
    max-height: 2px;
}}

#progress_thin::chunk {{
    background-color: {ACCENT};
    border-radius: 1px;
}}

/* ─── Log / Console ───────────────────────────────────────────────────────── */
QTextEdit#console {{
    background-color: {BG1};
    color: {TEXT2};
    border: none;
    border-top: 1px solid {BORDER};
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
    font-size: 11px;
    padding: 12px;
    line-height: 1.6;
}}

/* ─── Labels ──────────────────────────────────────────────────────────────── */
QLabel#label_section {{
    color: {TEXT2};
    font-size: 10px;
    letter-spacing: 1.5px;
    font-weight: 600;
}}

QLabel#stat_value {{
    color: {TEXT1};
    font-size: 22px;
    font-weight: 300;
    letter-spacing: -0.5px;
}}

QLabel#stat_label {{
    color: {TEXT3};
    font-size: 10px;
    letter-spacing: 1px;
}}

QLabel#progress_folder {{
    color: {ACCENT};
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}

QLabel#progress_file {{
    color: {TEXT2};
    font-size: 11px;
}}

/* ─── Scrollbar ───────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {BG3};
    border-radius: 3px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT3};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: transparent;
    height: 0;
}}

/* ─── Separator ───────────────────────────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {BORDER};
    background: {BORDER};
    border: none;
    max-height: 1px;
}}

/* ─── Tooltips ────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {BG2};
    color: {TEXT1};
    border: 1px solid {BORDER};
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 11px;
}}
"""
