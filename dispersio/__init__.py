"""Dispersio PDF."""
import os
import sys

__version__ = "1.17.1"
APP_NAME = "Dispersio PDF"
APP_ID = "DispersioPDF"
PROG_ID = "DispersioPDF.Document"
AUTHOR = "Lohan Lilson S. Lopes"
EMAIL = "lohanlilson@gmail.com"
COPYRIGHT = f"© 2026 {AUTHOR}"
# Repositório do GitHub (público) onde as versões são publicadas em Releases
UPDATE_REPO = "lohanlilson/DispersioPDF"
# nome antigo do repositório: usado se o novo ainda não existir (o GitHub redireciona o antigo depois da troca)
LEGACY_UPDATE_REPO = "lohanlilson/LumenPDF"
# identificadores do nome antigo (Lumen PDF): lidos só para migrar configurações e reconhecer o "leitor padrão"
LEGACY_APP_ID = "LumenPDF"
LEGACY_PROG_ID = "LumenPDF.Document"
LEGACY_APP_NAMES = ("Lumen PDF", "Dispersio PDF")


def resource(*parts):
    """Caminho de um recurso (funciona no código-fonte e no executável do PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)
