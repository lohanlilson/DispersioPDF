"""Tema visual inspirado no layout moderno de leitores PDF profissionais (claro e escuro)."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from . import icons

LIGHT = dict(
    bg="#f5f5f5", panel="#ffffff", canvas="#e9e9e9", border="#e1e1e1", text="#2c2c2c",
    muted="#6e6e6e", hover="#ececec", accent="#1473e6", accent_text="#ffffff",
    selected="#e5f0fd", tab="#ececec", input="#ffffff", danger="#d7373f",
)
DARK = dict(
    bg="#1f1f1f", panel="#2a2a2a", canvas="#151515", border="#3a3a3a", text="#e8e8e8",
    muted="#a5a5a5", hover="#363636", accent="#3b8ef0", accent_text="#ffffff",
    selected="#24384f", tab="#262626", input="#333333", danger="#ff5c63",
)

current = dict(LIGHT)
is_dark = False


def qss(c):
    return f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; font-size: 13px; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget#Panel, QWidget#HomePage, QWidget#ToolPanel, QWidget#SidePanel {{ background: {c['panel']}; }}
QWidget#ToolPanel {{ border-right: 1px solid {c['border']}; }}
QWidget#SidePanel {{ border-left: 1px solid {c['border']}; }}
QWidget#Rail {{ background: {c['panel']}; border-left: 1px solid {c['border']}; }}
QWidget#QuickRail {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QWidget#TopBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
QWidget#NavPill {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 18px; }}
QGraphicsView#Canvas {{ background: {c['canvas']}; border: none; }}
QLabel#Title {{ font-size: 22px; font-weight: 600; }}
QLabel#Section {{ color: {c['muted']}; font-size: 11px; font-weight: 600; text-transform: uppercase; padding: 10px 12px 4px 12px; }}
QLabel#Muted {{ color: {c['muted']}; }}
QMenuBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {c['hover']}; border-radius: 4px; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['selected']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
QTabWidget::pane {{ border: none; }}
QTabBar {{ background: {c['tab']}; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; margin-right: 1px; border: none; min-width: 80px; max-width: 240px; }}
QTabBar::tab:selected {{ background: {c['panel']}; border-top: 2px solid {c['accent']}; }}
QTabBar::tab:hover:!selected {{ background: {c['hover']}; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 6px; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:checked {{ background: {c['selected']}; }}
QToolButton#TopTab {{ padding: 7px 12px; font-weight: 600; }}
QToolButton#TopTab:checked {{ background: transparent; border-bottom: 2px solid {c['accent']}; border-radius: 0; color: {c['accent']}; }}
QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 16px; padding: 6px 16px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_text']}; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {c['accent']}; }}
QPushButton#ToolItem {{ text-align: left; border: none; border-radius: 6px; padding: 7px 10px; }}
QPushButton#ToolItem:hover {{ background: {c['hover']}; }}
QPushButton#Card {{ text-align: left; border: 1px solid {c['border']}; border-radius: 10px; padding: 14px; background: {c['panel']}; }}
QPushButton#Card:hover {{ border-color: {c['accent']}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {c['input']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px; }}
QLineEdit#Search {{ border-radius: 16px; padding: 6px 12px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; selection-background-color: {c['selected']}; }}
QListWidget, QTreeWidget, QTableWidget, QTextBrowser {{ background: {c['panel']}; border: none; outline: none; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {c['selected']}; color: {c['text']}; border-radius: 4px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['hover']}; }}
QHeaderView::section {{ background: {c['panel']}; border: none; border-bottom: 1px solid {c['border']}; padding: 4px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['border']}; color: {c['muted']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 12px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QProgressBar {{ border: 1px solid {c['border']}; border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 6px; }}
QSplitter::handle {{ background: {c['border']}; }}
QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}
"""


def apply(dark=False):
    global current, is_dark
    is_dark = dark
    current = dict(DARK if dark else LIGHT)
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
