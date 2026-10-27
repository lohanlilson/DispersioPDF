"""Tema visual do Dispersio PDF (claro e escuro), com a identidade violeta + dourado da marca."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from . import icons

BRAND = "#6d3cf0"        # violeta Dispersio
BRAND_2 = "#9b5cff"
GOLD = "#ffb547"         # o "lúmen"

LIGHT = dict(
    bg="#f6f5fb", panel="#ffffff", canvas="#ecebf3", border="#e6e3f0", text="#1f1d2b",
    muted="#6c6880", hover="#f2effa", accent=BRAND, accent_2=BRAND_2, accent_text="#ffffff",
    selected="#ece6fe", tab="#efedf6", input="#ffffff", danger="#e5484d", card="#ffffff",
    hero_1="#2a1b6e", hero_2="#6d3cf0", hero_3="#c0479b", shadow="rgba(40,20,90,0.10)",
)
DARK = dict(
    bg="#14121c", panel="#1c1a26", canvas="#0f0d16", border="#2c2939", text="#ecebf4",
    muted="#a19db6", hover="#262335", accent="#8b5cff", accent_2="#b48cff", accent_text="#ffffff",
    selected="#2e2554", tab="#17151f", input="#232030", danger="#ff6369", card="#211e2c",
    hero_1="#1d1450", hero_2="#4b27b8", hero_3="#9a3a85", shadow="rgba(0,0,0,0.35)",
)

current = dict(LIGHT)
is_dark = False


def qss(c):
    r = 10
    return f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', 'Noto Sans', sans-serif;
     font-size: {c.get('font_px', 13)}px; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget#Panel, QWidget#ToolPanel, QWidget#SidePanel {{ background: {c['panel']}; }}
QWidget#HomePage {{ background: {c['bg']}; }}
QWidget#ToolPanel {{ border-right: 1px solid {c['border']}; }}
QWidget#SidePanel {{ border-left: 1px solid {c['border']}; }}
QWidget#Rail {{ background: {c['panel']}; border-left: 1px solid {c['border']}; }}
QWidget#QuickRail {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QWidget#TopBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
QWidget#NavPill {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 20px; }}
QGraphicsView#Canvas {{ background: {c['canvas']}; border: none; }}

/* tela Início */
QFrame#Hero {{ border-radius: 18px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['hero_1']}, stop:0.6 {c['hero_2']}, stop:1 {c['hero_3']}); }}
QFrame#Hero QLabel {{ color: #ffffff; background: transparent; }}
QLabel#HeroTitle {{ font-size: 26px; font-weight: 700; }}
QLabel#HeroSub {{ font-size: 14px; color: rgba(255,255,255,0.82); }}
QPushButton#HeroPrimary {{ background: #ffffff; color: {c['hero_2']}; border: none; border-radius: 12px;
    padding: 10px 22px; font-weight: 700; font-size: 14px; }}
QPushButton#HeroPrimary:hover {{ background: #f3eeff; }}
QPushButton#HeroGhost {{ background: rgba(255,255,255,0.14); color: #ffffff; border: 1px solid rgba(255,255,255,0.35);
    border-radius: 12px; padding: 10px 18px; font-weight: 600; }}
QPushButton#HeroGhost:hover {{ background: rgba(255,255,255,0.24); }}
QLabel#H2 {{ font-size: 16px; font-weight: 700; }}
QPushButton#Card {{ text-align: left; border: 1px solid {c['border']}; border-radius: 14px; padding: 14px 14px;
    background: {c['card']}; }}
QPushButton#Card:hover {{ border-color: {c['accent']}; background: {c['hover']}; }}
QFrame#RecentCard {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#RecentCard:hover {{ border-color: {c['accent']}; }}
QFrame#RecentCard QLabel {{ background: transparent; }}
QLabel#RecentName {{ font-weight: 600; }}
QLabel#Thumb {{ background: {c['canvas']}; border-radius: 8px; }}

QLabel#Title {{ font-size: 22px; font-weight: 700; }}
QLabel#Section {{ color: {c['muted']}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px;
    padding: 12px 12px 4px 12px; }}
QLabel#Muted {{ color: {c['muted']}; }}
QMenuBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {c['hover']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 28px 7px 26px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['selected']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {c['tab']}; qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; margin: 5px 2px 0 2px; border: none;
    border-top-left-radius: 10px; border-top-right-radius: 10px; min-width: 80px; max-width: 240px; color: {c['muted']}; }}
QTabBar::tab:selected {{ background: {c['panel']}; color: {c['text']}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: {c['hover']}; color: {c['text']}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:checked {{ background: {c['selected']}; }}
QToolButton#TopTab {{ padding: 7px 14px; font-weight: 600; border-radius: 16px; color: {c['muted']}; }}
QToolButton#TopTab:hover {{ color: {c['text']}; }}
QToolButton#TopTab:checked {{ background: {c['selected']}; color: {c['accent']}; }}
QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: {r}px; padding: 7px 16px; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#Primary {{ color: {c['accent_text']}; border: none; font-weight: 600;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['accent']}, stop:1 {c['accent_2']}); }}
QPushButton#Primary:hover {{ background: {c['accent']}; }}
QPushButton#ToolItem {{ text-align: left; border: none; border-radius: 8px; padding: 6px 8px; }}
QPushButton#ToolItem:hover {{ background: {c['hover']}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 9px; }}
QLineEdit#Search {{ border-radius: 18px; padding: 7px 14px; background: {c['tab']}; border-color: transparent; }}
QLineEdit#Search:focus {{ background: {c['input']}; border-color: {c['accent']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px;
    selection-background-color: {c['selected']}; selection-color: {c['text']}; padding: 4px; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QListWidget, QTreeWidget, QTableWidget, QTextBrowser {{ background: {c['panel']}; border: none; outline: none; }}
QListWidget::item {{ border-radius: 8px; padding: 2px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['hover']}; }}
QHeaderView::section {{ background: {c['panel']}; border: none; border-bottom: 1px solid {c['border']}; padding: 6px; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['border']}; color: {c['muted']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 12px; margin-top: 14px; padding: 10px 8px 8px 8px;
    background: {c['panel']}; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {c['muted']}; }}
QProgressBar {{ border: none; border-radius: 6px; text-align: center; background: {c['tab']}; min-height: 12px; }}
QProgressBar::chunk {{ border-radius: 6px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['accent']}, stop:1 {c['accent_2']}); }}
QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['accent']}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QSplitter::handle {{ background: {c['border']}; }}
QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px; }}
"""


def system_is_dark():
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def apply(dark=False, accent=None, font_px=13, canvas=None):
    """Aplica o tema. dark pode ser True/False ou 'system'."""
    global current, is_dark
    if dark == "system":
        dark = system_is_dark()
    elif isinstance(dark, str):
        dark = dark == "dark"
    is_dark = bool(dark)
    current = dict(DARK if is_dark else LIGHT)
    if accent:
        current["accent"] = accent
        from PySide6.QtGui import QColor as _C
        lighter = _C(accent).lighter(135 if not is_dark else 125)
        current["accent_2"] = lighter.name()
        a = _C(accent)
        sel = _C(a)
        sel.setAlpha(255)
        base = _C(current["panel"])
        mix = 0.18 if not is_dark else 0.30
        current["selected"] = _C(int(base.red() * (1 - mix) + a.red() * mix), int(base.green() * (1 - mix) + a.green() * mix),
                                 int(base.blue() * (1 - mix) + a.blue() * mix)).name()
    if canvas:
        current["canvas"] = canvas
    current["font_px"] = font_px
    app = QApplication.instance()
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(current["bg"]))
    pal.setColor(QPalette.Base, QColor(current["input"]))
    pal.setColor(QPalette.Text, QColor(current["text"]))
    pal.setColor(QPalette.WindowText, QColor(current["text"]))
    pal.setColor(QPalette.Button, QColor(current["panel"]))
    pal.setColor(QPalette.ButtonText, QColor(current["text"]))
    pal.setColor(QPalette.Highlight, QColor(current["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setStyleSheet(qss(current))
    icons.set_color(current["text"])
    for w in app.topLevelWidgets():
        style_titlebar(w)


def style_titlebar(widget):
    """Windows 11: barra de título na cor do tema (clara/escura) e cantos arredondados."""
    import sys
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1 if is_dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))      # modo escuro
        col = QColor(current["panel"])
        ref = ctypes.c_int(col.red() | (col.green() << 8) | (col.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(ref), ctypes.sizeof(ref))        # cor da barra
        txt = QColor(current["text"])
        tref = ctypes.c_int(txt.red() | (txt.green() << 8) | (txt.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(tref), ctypes.sizeof(tref))      # cor do texto
        corner = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))  # cantos arredondados
    except Exception:
        pass


def apply_from_config():
    from .config import cfg, UI_FONT_PX
    apply(cfg.get("theme"), cfg.get("accent"), UI_FONT_PX.get(cfg.get("ui_size"), 13), cfg.get("canvas_color") or None)
