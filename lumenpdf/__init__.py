"""Lumen PDF."""
import os
import sys

__version__ = "1.3.3"
APP_NAME = "Lumen PDF"
APP_ID = "LumenPDF"
PROG_ID = "LumenPDF.Document"
AUTHOR = "Lohan Lilson S. Lopes"
EMAIL = "lohanlilson@gmail.com"
COPYRIGHT = f"© 2026 {AUTHOR}"
# Repositório do GitHub (público) onde as versões são publicadas em Releases
UPDATE_REPO = "lohanlilson/LumenPDF"


def resource(*parts):
    """Caminho de um recurso (funciona no código-fonte e no executável do PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)
